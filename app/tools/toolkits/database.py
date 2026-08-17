# app/tools/toolkits/database.py
from app.tools.base import Toolkit


class DatabaseTools(Toolkit):
    namespace = "database"

    def __init__(self):
        pass

    def query(self, sql: str, params: list | None = None) -> list[dict]:
        """Run a SQL query with optional bound parameters and return the resulting rows."""
        raise NotImplementedError("Database query is not implemented yet.")

    def transaction(
        self,
        statements: list[str],
        params: list[list] | None = None,
    ) -> str:
        """Run multiple SQL statements as a single atomic transaction."""
        raise NotImplementedError("Database transactions are not implemented yet.")