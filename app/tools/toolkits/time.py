from datetime import datetime
from zoneinfo import ZoneInfo

from app.tools.base import Toolkit


class TimeTools(Toolkit):
    namespace = "time"

    def __init__(self):
        pass

    def current(self, timezone: str = "UTC") -> str:
        """Get the current date and time in the given timezone."""
        return datetime.now(ZoneInfo(timezone)).isoformat()