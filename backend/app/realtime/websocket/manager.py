from fastapi import WebSocket


class ConnectionManager:

    def __init__(self):

        self.active_connections = {}

    async def connect(

        self,

        session_id: str,

        websocket: WebSocket,

    ):

        await websocket.accept()

        self.active_connections[
            session_id
        ] = websocket

    def disconnect(

        self,

        session_id: str,

    ):

        if (
            session_id
            in self.active_connections
        ):

            del self.active_connections[
                session_id
            ]

    async def send_message(

        self,

        session_id: str,

        message: dict,

    ):

        websocket = (
            self.active_connections.get(
                session_id
            )
        )

        if websocket:

            await websocket.send_json(
                message
            )


manager = ConnectionManager()