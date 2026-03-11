import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import Settings
from bot.sender import OutputSender
from bot.session_manager import SessionManager

logger = logging.getLogger(__name__)
router = Router()


def _sessions_keyboard(sm: SessionManager) -> InlineKeyboardMarkup:
    """Build inline keyboard with session list."""
    buttons = []
    for name in sm.session_names:
        label = f"✓ {name}" if name == sm.active_name else name
        buttons.append(
            InlineKeyboardButton(
                text=label, callback_data=f"session:switch:{name}"
            )
        )
    rows = [[btn] for btn in buttons]
    rows.append(
        [InlineKeyboardButton(text="＋ New session", callback_data="session:new")]
    )
    # Add delete button for non-active sessions
    delete_buttons = [
        InlineKeyboardButton(
            text=f"✕ {name}", callback_data=f"session:delete:{name}"
        )
        for name in sm.session_names
        if name != sm.active_name
    ]
    if delete_buttons:
        rows.extend([[btn] for btn in delete_buttons])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _sessions_text(sm: SessionManager) -> str:
    lines = ["<b>Sessions</b>"]
    for name in sm.session_names:
        active_marker = " ← active" if name == sm.active_name else ""
        session = sm._sessions[name]
        status = "busy" if session.is_busy else ("alive" if session.is_alive else "dead")
        lines.append(f"  • <code>{html.escape(name)}</code> [{status}]{active_marker}")
    return "\n".join(lines)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "<b>Terminal Bot</b>\n\n"
        "Send any text to execute it as a shell command.\n\n"
        "<b>Commands:</b>\n"
        "/cancel — cancel running command\n"
        "/reset — restart current shell session\n"
        "/sessions — manage sessions\n"
        "/new [name] — create new session\n"
        "/help — show this message",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, session_manager: SessionManager) -> None:
    shell = session_manager.active
    if shell.is_busy:
        await shell.cancel()
        await message.answer("<i>Command cancelled.</i>", parse_mode="HTML")
    else:
        await message.answer("<i>No command is running.</i>", parse_mode="HTML")


@router.message(Command("reset"))
async def cmd_reset(message: Message, session_manager: SessionManager) -> None:
    await session_manager.active.reset()
    await message.answer(
        f"<i>Session '<code>{html.escape(session_manager.active_name)}</code>' reset.</i>",
        parse_mode="HTML",
    )


@router.message(Command("sessions"))
async def cmd_sessions(message: Message, session_manager: SessionManager) -> None:
    await message.answer(
        _sessions_text(session_manager),
        parse_mode="HTML",
        reply_markup=_sessions_keyboard(session_manager),
    )


@router.message(Command("new"))
async def cmd_new_session(message: Message, session_manager: SessionManager) -> None:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "<i>Usage: /new &lt;name&gt;</i>", parse_mode="HTML"
        )
        return

    name = args[1].strip()
    if not name.replace("-", "").replace("_", "").isalnum():
        await message.answer(
            "<i>Session name must be alphanumeric (dashes and underscores allowed).</i>",
            parse_mode="HTML",
        )
        return

    try:
        await session_manager.create(name)
        await session_manager.switch(name)
        await message.answer(
            f"<i>Created and switched to session '<code>{html.escape(name)}</code>'.</i>",
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(f"<i>{html.escape(str(e))}</i>", parse_mode="HTML")


# --- Callback handlers ---

@router.callback_query(F.data == "session:new")
async def cb_new_session(callback: CallbackQuery, session_manager: SessionManager) -> None:
    await callback.answer()
    await callback.message.answer(
        "Send the name for the new session: <code>/new &lt;name&gt;</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("session:switch:"))
async def cb_switch_session(
    callback: CallbackQuery, session_manager: SessionManager
) -> None:
    name = callback.data.split(":", 2)[2]
    if name == session_manager.active_name:
        await callback.answer(f"Already on '{name}'")
        return

    try:
        await session_manager.switch(name)
        await callback.answer(f"Switched to '{name}'")
        await callback.message.edit_text(
            _sessions_text(session_manager),
            parse_mode="HTML",
            reply_markup=_sessions_keyboard(session_manager),
        )
    except KeyError:
        await callback.answer("Session not found", show_alert=True)


@router.callback_query(F.data.startswith("session:delete:"))
async def cb_delete_session(
    callback: CallbackQuery, session_manager: SessionManager
) -> None:
    name = callback.data.split(":", 2)[2]
    try:
        await session_manager.delete(name)
        await callback.answer(f"Deleted '{name}'")
        await callback.message.edit_text(
            _sessions_text(session_manager),
            parse_mode="HTML",
            reply_markup=_sessions_keyboard(session_manager),
        )
    except (KeyError, ValueError) as e:
        await callback.answer(str(e), show_alert=True)


@router.message()
async def handle_shell_command(
    message: Message, session_manager: SessionManager, bot: Bot, settings: Settings
) -> None:
    if not message.text:
        return

    shell = session_manager.active

    # If shell is busy, forward as stdin input
    if shell.is_busy:
        await shell.send_input(message.text)
        try:
            await message.delete()
        except Exception:
            pass
        return

    sender = OutputSender(bot, message.chat.id, settings.OUTPUT_UPDATE_INTERVAL)
    await sender.send_initial(message.text)
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
