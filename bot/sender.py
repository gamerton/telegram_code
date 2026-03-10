import asyncio
import html
import logging
import time

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import Message

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000


class OutputSender:
    def __init__(
        self, bot: Bot, chat_id: int, update_interval: float = 2.0
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._update_interval = update_interval
        self._current_message: Message | None = None
        self._last_sent_text: str = ""
        self._last_edit_time: float = 0
        self._poll_task: asyncio.Task | None = None
        self._shell = None
        self._finished = False

    async def send_initial(self, command_text: str) -> None:
        """Send the initial 'executing' message."""
        escaped = html.escape(command_text)
        text = f"<b>$ {escaped}</b>\n<i>executing...</i>"
        self._current_message = await self._bot.send_message(
            self._chat_id, text, parse_mode=ParseMode.HTML
        )
        self._last_edit_time = time.monotonic()

    def start_polling(self, shell) -> None:
        """Start background task that polls shell.output_buffer and updates Telegram."""
        self._shell = shell
        self._finished = False
        self._poll_task = asyncio.create_task(self._poll_loop())

    def stop_polling(self) -> None:
        """Stop the background polling task."""
        self._finished = True
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = None

    async def _poll_loop(self) -> None:
        """Periodically check shell buffer and update Telegram message."""
        try:
            while not self._finished:
                await asyncio.sleep(self._update_interval)
                if self._finished:
                    break

                if self._shell and self._shell.output_buffer:
                    current = self._shell.output_buffer
                    if current != self._last_sent_text:
                        await self._do_edit(current, running=True)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Poll loop error: %s", e)

    async def _do_edit(self, output: str, running: bool = False) -> None:
        """Edit current message with output, rate-limited."""
        now = time.monotonic()
        if now - self._last_edit_time < self._update_interval:
            return

        if not output or output == self._last_sent_text:
            return

        # If output is too long, show only the tail
        display = output
        if len(display) > MAX_MESSAGE_LENGTH - 100:
            display = "...\n" + display[-(MAX_MESSAGE_LENGTH - 100):]

        suffix = "\n<i>running...</i>" if running else ""
        text = f"<pre>{html.escape(display)}</pre>{suffix}"

        try:
            if self._current_message:
                await self._current_message.edit_text(
                    text, parse_mode=ParseMode.HTML
                )
                self._last_sent_text = output
                self._last_edit_time = now
        except Exception as e:
            logger.debug("Edit failed: %s", e)

    async def send_output(self, output: str, is_final: bool, exit_code: int | None) -> None:
        """Send or update the output message."""
        if is_final:
            self.stop_polling()
            await self._finalize(output, exit_code)
        else:
            # Intermediate updates are handled by polling loop,
            # but we also update here if enough time has passed
            await self._do_edit(output, running=True)

    async def _finalize(self, output: str, exit_code: int | None) -> None:
        """Send the final output, splitting into chunks if needed."""
        if not output and exit_code is not None:
            suffix = self._exit_suffix(exit_code)
            text = f"<i>{suffix}</i>"
            await self._safe_edit_or_send(text)
            return

        # Split output into chunks
        chunks = self._split_chunks(output)

        for i, chunk in enumerate(chunks):
            escaped = html.escape(chunk)
            is_last = i == len(chunks) - 1

            if is_last and exit_code is not None:
                suffix = self._exit_suffix(exit_code)
                text = f"<pre>{escaped}</pre>\n<i>{suffix}</i>"
            else:
                text = f"<pre>{escaped}</pre>"

            if i == 0 and self._current_message:
                await self._safe_edit_or_send(text)
            else:
                await self._safe_send(text)

    async def _safe_edit_or_send(self, text: str) -> None:
        """Try to edit the current message, fall back to sending a new one."""
        try:
            if self._current_message:
                await self._current_message.edit_text(
                    text, parse_mode=ParseMode.HTML
                )
                return
        except Exception as e:
            logger.debug("Edit failed, sending new message: %s", e)
        await self._safe_send(text)

    async def _safe_send(self, text: str) -> None:
        """Send a new message, handling potential errors."""
        try:
            self._current_message = await self._bot.send_message(
                self._chat_id, text, parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error("Failed to send message: %s", e)

    @staticmethod
    def _split_chunks(text: str) -> list[str]:
        """Split text into chunks that fit within Telegram's message limit."""
        if len(text) <= MAX_MESSAGE_LENGTH:
            return [text]

        chunks = []
        while text:
            if len(text) <= MAX_MESSAGE_LENGTH:
                chunks.append(text)
                break

            # Try to split at a newline
            split_pos = text.rfind("\n", 0, MAX_MESSAGE_LENGTH)
            if split_pos == -1:
                split_pos = MAX_MESSAGE_LENGTH

            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip("\n")

        return chunks

    @staticmethod
    def _exit_suffix(exit_code: int) -> str:
        if exit_code == 0:
            return "exit: 0"
        return f"exit: {exit_code}"
