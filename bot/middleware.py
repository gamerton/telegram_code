import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    def __init__(self, authorized_user_id: int) -> None:
        self._authorized_user_id = authorized_user_id

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if not event.from_user or event.from_user.id != self._authorized_user_id:
            user_id = event.from_user.id if event.from_user else "unknown"
            username = event.from_user.username if event.from_user else "unknown"
            logger.warning(
                "Unauthorized access attempt: user_id=%s username=%s text=%s",
                user_id,
                username,
                event.text,
            )
            return None

        return await handler(event, data)
