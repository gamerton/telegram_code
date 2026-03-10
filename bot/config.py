import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Settings:
    BOT_TOKEN: str
    AUTHORIZED_USER_ID: int
    COMMAND_TIMEOUT: int = 300
    MAX_MESSAGE_LENGTH: int = 4000
    OUTPUT_UPDATE_INTERVAL: float = 2.0
    SHELL_EXECUTABLE: str = "/bin/bash"

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()

        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            raise ValueError("BOT_TOKEN is required in .env")

        user_id = os.getenv("AUTHORIZED_USER_ID")
        if not user_id:
            raise ValueError("AUTHORIZED_USER_ID is required in .env")

        return cls(
            BOT_TOKEN=bot_token,
            AUTHORIZED_USER_ID=int(user_id),
            COMMAND_TIMEOUT=int(os.getenv("COMMAND_TIMEOUT", "300")),
            OUTPUT_UPDATE_INTERVAL=float(os.getenv("OUTPUT_UPDATE_INTERVAL", "2.0")),
        )
