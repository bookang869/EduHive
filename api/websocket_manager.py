from fastapi import WebSocket

class ConnectionManager:
  def __init__(self):
    self.active_connections: list[WebSocket] = []

  async def connect(self, websocket: WebSocket):
    await websocket.accept()
    # add a new user to the list of active connections
    self.active_connections.append(websocket)

  def disconnect(self, websocket: WebSocket):
    self.active_connections.remove(websocket)
  
  async def send_personal_message(self, message: str, websocket: WebSocket):
    await websocket.send_text(message)
  
  async def broadcast(self, message: str, skip: WebSocket | None = None):
    for connection in self.active_connections:
      if connection is skip:
        continue
      await connection.send_text(message)

manager = ConnectionManager()