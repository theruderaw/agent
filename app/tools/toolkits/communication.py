# app/tools/toolkits/communication.py
from app.tools.base import Toolkit


class CommunicationTools(Toolkit):
    namespace = "communication"

    def __init__(self):
        pass

    def message(self, to: str, body: str) -> str:
        """Send a direct message to the given recipient."""
        raise NotImplementedError("Direct messaging is not implemented yet.")

    def email(self, to: str, subject: str, body: str) -> str:
        """Send an email to the given address with a subject and body."""
        raise NotImplementedError("Email sending is not implemented yet.")