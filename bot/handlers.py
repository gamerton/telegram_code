import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Settings
from bot.sender import OutputSender
from bot.shell import ShellSession

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "<b>Terminal Bot</b>\n\n"
        "Send any text to execute it as a shell command.\n\n"
        "<b>Commands:</b>\n"
        "/cancel — cancel running command\n"
        "/reset — restart shell session\n"
        "/help — show this message",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, shell: ShellSession) -> None:
    if shell.is_busy:
        await shell.cancel()
        await message.answer("<i>Command cancelled.</i>", parse_mode="HTML")
    else:
        await message.answer("<i>No command is running.</i>", parse_mode="HTML")


@router.message(Command("reset"))
async def cmd_reset(message: Message, shell: ShellSession) -> None:
    await shell.reset()
    await message.answer("<i>Shell session reset.</i>", parse_mode="HTML")


@router.message()
async def handle_shell_command(
    message: Message, shell: ShellSession, bot: Bot, settings: Settings
) -> None:
    if not message.text:
        return

    # If shell is busy, forward as stdin input
    if shell.is_busy:
        await shell.send_input(message.text)
        # Delete the user's input message
        try:
            await message.delete()
        except Exception:
            pass
        return

    sender = OutputSender(bot, message.chat.id, settings.OUTPUT_UPDATE_INTERVAL)
    await sender.send_initial(message.text)

    # Start background polling — sender will periodically check
    # shell.output_buffer and update the Telegram message automatically
    sender.start_polling(shell)

    try:
        async for output, is_final, exit_code in shell.execute(
            message.text, settings.COMMAND_TIMEOUT
        ):
            await sender.send_output(output, is_final, exit_code)
    except Exception as e:
        sender.stop_polling()
        logger.exception("Error executing command")
        await message.answer(
            f"<pre>Error: {e}</pre>", parse_mode="HTML"
        )
