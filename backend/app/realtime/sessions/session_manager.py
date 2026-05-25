class SessionManager:

    def __init__(self):

        self.sessions = {}

    def create_session(

        self,

        session_id: str,

        initial_state: dict,

    ):

        self.sessions[
            session_id
        ] = initial_state

    def get_session(

        self,

        session_id: str,

    ):

        return self.sessions.get(
            session_id
        )

    def update_session(

        self,

        session_id: str,

        state: dict,

    ):

        self.sessions[
            session_id
        ] = state


session_manager = (
    SessionManager()
)