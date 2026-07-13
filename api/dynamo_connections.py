"""
DynamoDB connection manager for API Gateway WebSocket.
Maps connection_id → session_id across Lambda invocations.
"""

import os
import time
import logging
import boto3
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
CONNECTIONS_TABLE = os.environ.get("CONNECTIONS_TABLE", "eduhive-connections")

_table = None


def _get_table():
    global _table
    if _table is None:
        dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        _table = dynamodb.Table(CONNECTIONS_TABLE)
    return _table


def save_connection(connection_id: str, session_id: str, client_id: str = "unknown") -> None:
    """Store connection_id → session_id mapping. Called on $connect."""
    table = _get_table()
    table.put_item(Item={
        "connectionId": connection_id,
        "sessionId": session_id,
        "clientId": client_id,
        "connectedAt": int(time.time()),
        "ttl": int(time.time()) + 86400,  # 24h auto-cleanup
    })
    logger.info(f"Saved connection {connection_id} for session {session_id}")


def get_connection(connection_id: str) -> Optional[Dict[str, Any]]:
    """Look up session_id from connection_id. Called on $default."""
    table = _get_table()
    response = table.get_item(
        Key={"connectionId": connection_id},
        ConsistentRead=True,
    )
    return response.get("Item")


def delete_connection(connection_id: str) -> None:
    """Remove connection mapping. Called on $disconnect."""
    table = _get_table()
    table.delete_item(Key={"connectionId": connection_id})
    logger.info(f"Deleted connection {connection_id}")
