"""
Lambda handler for API Gateway WebSocket events.
Processes $connect, $disconnect, and $default (message) routes.
Uses DynamoDB for connection mapping and LangGraph checkpointing.
"""

import json
import os
import logging
import asyncio
import boto3
from typing import Dict, Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph_checkpoint_dynamodb.saver import DynamoDBSaver

from api.dynamo_connections import save_connection, get_connection, delete_connection

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
CHECKPOINTS_TABLE = os.environ.get("CHECKPOINTS_TABLE", "eduhive-checkpoints")
WRITES_TABLE = os.environ.get("WRITES_TABLE", "eduhive-writes")

# Module-level globals reused across Lambda invocations within same container
_graph = None
_loop = None


def get_or_create_loop():
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def init_graph():
    """Initialize graph with DynamoDB checkpointer. No async context manager needed."""
    global _graph
    if _graph is not None:
        return _graph

    from core.graph import build_graph

    checkpointer = DynamoDBSaver(
        checkpoints_table_name=CHECKPOINTS_TABLE,
        writes_table_name=WRITES_TABLE,
        client_config={"region_name": AWS_REGION},
    )

    _graph = build_graph(checkpointer=checkpointer)
    logger.info("Graph initialized with DynamoDB checkpointer")
    return _graph


def send_message(connection_id: str, domain_name: str, stage: str, message: str) -> None:
    """Send a message back to a WebSocket client via API Gateway Management API."""
    endpoint_url = f"https://{domain_name}/{stage}"
    apigw_client = boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=endpoint_url,
    )

    try:
        apigw_client.post_to_connection(
            ConnectionId=connection_id,
            Data=message.encode("utf-8"),
        )
    except apigw_client.exceptions.GoneException:
        logger.warning(f"Connection {connection_id} is gone")
    except Exception as e:
        logger.error(f"Error sending message to {connection_id}: {e}")
        raise


async def process_message_async(graph, session_id: str, message_text: str) -> str:
    """Process a message through the LangGraph agent."""
    config = {"configurable": {"thread_id": session_id}}
    prompt = HumanMessage(content=message_text)
    result = await graph.ainvoke({"messages": [prompt]}, config=config)

    messages = result.get("messages", [])
    if not messages:
        return "Error: No response generated"
    return messages[-1].content


def handle_connect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle $connect: store connection_id → session_id mapping in DynamoDB."""
    request_context = event.get("requestContext", {})
    connection_id = request_context.get("connectionId")
    query_params = event.get("queryStringParameters") or {}
    session_id = query_params.get("session_id")
    client_id = query_params.get("client_id", "unknown")

    if not session_id:
        logger.error("$connect missing session_id in query params")
        return {"statusCode": 400, "body": "session_id is required"}

    save_connection(connection_id, session_id, client_id)
    return {"statusCode": 200, "body": "Connected"}


def handle_disconnect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle $disconnect: remove connection mapping from DynamoDB."""
    request_context = event.get("requestContext", {})
    connection_id = request_context.get("connectionId")

    delete_connection(connection_id)
    return {"statusCode": 200, "body": "Disconnected"}


def handle_default(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle $default: look up session from DynamoDB, process message, send response."""
    request_context = event.get("requestContext", {})
    connection_id = request_context.get("connectionId")
    domain_name = request_context.get("domainName")
    stage = request_context.get("stage")
    body = event.get("body", "")

    if not body:
        return {"statusCode": 400, "body": "No message body"}

    # Parse message
    session_id = None
    try:
        message_data = json.loads(body)
        message_text = message_data.get("message", body)
        session_id_from_body = message_data.get("session_id")
    except (json.JSONDecodeError, TypeError):
        message_text = body
        session_id_from_body = None

    # Look up session_id from DynamoDB (primary), fall back to message body
    conn = get_connection(connection_id)
    if conn:
        session_id = conn["sessionId"]
    elif session_id_from_body:
        session_id = session_id_from_body
        logger.warning(f"Connection {connection_id} not found in DynamoDB, using session_id from body")

    if not session_id:
        error_msg = "Session not found. Please reconnect."
        send_message(connection_id, domain_name, stage, error_msg)
        return {"statusCode": 400, "body": "session_id not found"}

    # Process through LangGraph
    graph = init_graph()
    loop = get_or_create_loop()
    try:
        response_text = loop.run_until_complete(
            process_message_async(graph, session_id, message_text)
        )
        send_message(connection_id, domain_name, stage, response_text)
        return {"statusCode": 200, "body": "Message processed"}
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        try:
            send_message(connection_id, domain_name, stage, f"Error: {str(e)}")
        except Exception:
            pass
        return {"statusCode": 500, "body": str(e)}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda entry point for API Gateway WebSocket events."""
    try:
        route_key = event.get("requestContext", {}).get("routeKey")
        logger.info(f"Route: {route_key}")

        if route_key == "$connect":
            return handle_connect(event)
        elif route_key == "$disconnect":
            return handle_disconnect(event)
        elif route_key == "$default":
            return handle_default(event)
        else:
            logger.warning(f"Unknown route: {route_key}")
            return {"statusCode": 400, "body": f"Unknown route: {route_key}"}
    except Exception as e:
        logger.error(f"Fatal error in lambda_handler: {e}", exc_info=True)
        return {"statusCode": 500, "body": f"Internal error: {str(e)}"}
