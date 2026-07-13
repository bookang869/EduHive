"""
Router handler that routes events to either HTTP (Mangum) or WebSocket handler
based on the event type. This allows a single Lambda function to handle both.
"""
print("ROUTER: Module loading...")
from typing import Dict, Any
print("ROUTER: Module loaded, handler function defined")

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler that routes events based on type.
    
    - WebSocket events: Have 'routeKey' in requestContext
    - HTTP events: Standard API Gateway HTTP events
    """
    print("ROUTER: Handler called")
    try:
        # Check if this is a WebSocket event
        # Both WebSocket API Gateway and Lambda Function URLs set routeKey to "$default",
        # but only WebSocket events have connectionId in requestContext.
        request_context = event.get('requestContext', {})
        connection_id = request_context.get('connectionId')
        route_key = request_context.get('routeKey')

        print(f"ROUTER: route_key = {route_key}, connectionId = {connection_id}")

        if connection_id and route_key in ("$connect", "$disconnect", "$default"):
            # This is a WebSocket event - route to WebSocket handler
            print("ROUTER: Importing websocket_handler...")
            from api.websocket_handler import lambda_handler as ws_handler
            print("ROUTER: Calling websocket_handler...")
            return ws_handler(event, context)
        else:
            # This is an HTTP event - route to Mangum handler
            print("ROUTER: Importing main handler...")
            from api.main import handler
            print("ROUTER: Calling main handler...")
            return handler(event, context)
    except Exception as e:
        print(f"ROUTER ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise