import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    def __init__(self, authorized_user_id: int) -> None:
        self._authorized_user_id = authorized_user_id

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if not from_user or from_user.id != self._authorized_user_id:
            user_id = from_user.id if from_user else "unknown"
            username = from_user.username if from_user else "unknown"
            logger.warning(
                "Unauthorized access attempt: user_id=%s username=%s",
                user_id,
                username,
            )
            return None

        return await handler(event, data)
