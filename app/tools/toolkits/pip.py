from app.tools.base import Toolkit


class PipTools(Toolkit):
    namespace = "pip"

    def __init__(self):
        ...

    def install(self, packages: list[str]) -> str:
        """Install Python packages."""
        ...

    def uninstall(self, packages: list[str]) -> str:
        """Uninstall Python packages."""
        ...

    def list_installed(self) -> str:
        """List installed Python packages."""
        ...

    def show(self, package: str) -> str:
        """Show information about an installed Python package."""
        ...

    def freeze(self) -> str:
        """List installed packages in requirements format."""
        ...

    def check(self) -> str:
        """Check installed packages for dependency conflicts."""
        ...

    def upgrade(self, packages: list[str]) -> str:
        """Upgrade Python packages."""
        ...