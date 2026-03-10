import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Settings
from bot.handlers import router
from bot.middleware import AuthMiddleware
from bot.shell import ShellSession

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

    shell = ShellSession(settings.SHELL_EXECUTABLE)
    await shell.start()

    # Authorization middleware
    dp.message.middleware(AuthMiddleware(settings.AUTHORIZED_USER_ID))

    # Dependency injection
    dp["shell"] = shell
    dp["settings"] = settings

    # Register handlers
    dp.include_router(router)

    try:
        await dp.start_polling(bot)
    finally:
        await shell.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
