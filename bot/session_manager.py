import logging

from bot.shell import ShellSession

logger = logging.getLogger(__name__)

DEFAULT_SESSION_NAME = "main"


class SessionManager:
    def __init__(self, shell_executable: str = "/bin/bash") -> None:
        self._shell_executable = shell_executable
        self._sessions: dict[str, ShellSession] = {}
        self._active_name: str = DEFAULT_SESSION_NAME

    async def initialize(self) -> None:
        """Create and start the default session."""
        session = ShellSession(self._shell_executable)
        await session.start()
        self._sessions[DEFAULT_SESSION_NAME] = session

    @property
    def active_name(self) -> str:
        return self._active_name

    @property
    def active(self) -> ShellSession:
        return self._sessions[self._active_name]

    @property
    def session_names(self) -> list[str]:
        return list(self._sessions.keys())

    def exists(self, name: str) -> bool:
        return name in self._sessions

    async def create(self, name: str) -> ShellSession:
        """Create a new named session and return it (does not switch to it)."""
        if name in self._sessions:
            raise ValueError(f"Session '{name}' already exists")
        session = ShellSession(self._shell_executable)
        await session.start()
        self._sessions[name] = session
        logger.info("Created session '%s'", name)
        return session

    async def switch(self, name: str) -> None:
        """Switch active session to the given name."""
        if name not in self._sessions:
            raise KeyError(f"Session '{name}' not found")
        self._active_name = name
        logger.info("Switched to session '%s'", name)

    async def delete(self, name: str) -> None:
        """Delete a session (cannot delete the active one)."""
        if name not in self._sessions:
            raise KeyError(f"Session '{name}' not found")
        if name == self._active_name:
            raise ValueError("Cannot delete the active session")
        await self._sessions[name].close()
        del self._sessions[name]
        logger.info("Deleted session '%s'", name)

    async def close_all(self) -> None:
        """Close all sessions."""
        for session in self._sessions.values():
            await session.close()
        self._sessions.clear()
