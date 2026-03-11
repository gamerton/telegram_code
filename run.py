import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Settings
from bot.handlers import router
from bot.middleware import AuthMiddleware
from bot.session_manager import SessionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = Settings.load()
    logger.info("Starting bot for user_id=%s", settings.AUTHORIZED_USER_ID)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    session_manager = SessionManager(settings.SHELL_EXECUTABLE)
    await session_manager.initialize()

    # Authorization middleware
    auth = AuthMiddleware(settings.AUTHORIZED_USER_ID)
    dp.message.middleware(auth)
    dp.callback_query.middleware(auth)

    # Dependency injection
    dp["session_manager"] = session_manager
    dp["settings"] = settings

    # Register handlers
    dp.include_router(router)

    try:
        await dp.start_polling(bot)
    finally:
        await session_manager.close_all()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
