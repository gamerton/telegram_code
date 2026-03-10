import asyncio
import fcntl
import logging
import os
import pty
import re
import signal
import struct
import subprocess
from uuid import uuid4
import base64

import pyte

logger = logging.getLogger(__name__)

TERM_COLS = 120
TERM_ROWS = 40


class ShellSession:
    def __init__(self, shell_executable: str = "/bin/bash") -> None:
        self._shell_executable = shell_executable
        self._master_fd: int | None = None
        self._process: subprocess.Popen | None = None
        self._lock = asyncio.Lock()
        self._running_command = False
        # Virtual terminal emulator
        self._screen = pyte.Screen(TERM_COLS, TERM_ROWS)
        self._stream = pyte.Stream(self._screen)
        # Public: rendered screen for sender to read
        self.output_buffer: str = ""
        # History of lines scrolled off-screen
        self._history_lines: list[str] = []
        self._screen.set_mode(pyte.modes.LNM)
        # To signal running executes to abort cleanly
        self._abort_event = asyncio.Event()

    def _render_screen(self) -> str:
        """Render the current virtual terminal screen to text."""
        lines = []
        for row in range(self._screen.lines):
            line = self._screen.display[row].rstrip()
            lines.append(line)
        # Strip Claude Code welcome banner if present
        # Из-за особенностей рендера ищем начало рамки на первых строках, а не только на самой первой
        start_idx = next(
            (i for i, line in enumerate(lines[:5]) if "╭" in line and "Claude Code" in line),
            None
        )
        if start_idx is not None:
            end_idx = next(
                (i for i, line in enumerate(lines[start_idx:]) if "╰" in line),
                None
            )
            if end_idx is not None:
                # Отрезаем всё с верхней рамки до нижней
                lines = lines[:start_idx] + lines[start_idx + end_idx + 1:]

        # Remove trailing empty lines
        while lines and not lines[-1]:
            lines.pop()
        screen_text = "\n".join(lines)

        # Prepend history if any
        if self._history_lines:
            hist = "\n".join(self._history_lines)
            if screen_text:
                return hist + "\n" + screen_text
            return hist
        return screen_text

    def _setup_history_callback(self) -> None:
        """Capture lines scrolled off the top of the screen."""
        original_index = self._screen.index

        def _index_with_history():
            # If cursor is at the bottom, the top line is about to scroll off
            if self._screen.cursor.y == self._screen.lines - 1:
                top_line = self._screen.display[0].rstrip()
                if top_line:
                    self._history_lines.append(top_line)
            original_index()

        self._screen.index = _index_with_history

    async def start(self) -> None:
        master_fd, slave_fd = pty.openpty()

        winsize = struct.pack("HHHH", TERM_ROWS, TERM_COLS, 0, 0)
        fcntl.ioctl(slave_fd, 0x5414, winsize)  # TIOCSWINSZ

        self._process = subprocess.Popen(
            [self._shell_executable, "--norc", "--noprofile"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
            env={**os.environ, "PS1": "", "PS2": "", "TERM": "xterm-256color"},
        )
        os.close(slave_fd)

        self._master_fd = master_fd

        # Set non-blocking
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Reset virtual screen
        self._screen.reset()
        self._history_lines.clear()
        self._setup_history_callback()

        # Initialize: clear prompt
        os.write(master_fd, b"PS1=''\nPS2=''\n")

        # Drain startup output
        await asyncio.sleep(0.3)
        self._drain_to_screen()

        # Clear screen state from init commands
        self._screen.reset()
        self._history_lines.clear()
        self._setup_history_callback()
        self._abort_event.clear()

        logger.info("Shell session started (pid=%s)", self._process.pid)

    def _drain_to_screen(self) -> None:
        """Read all available PTY data and feed to virtual screen."""
        while True:
            try:
                data = os.read(self._master_fd, 4096)
                self._stream.feed(data.decode("utf-8", errors="replace"))
            except (OSError, BlockingIOError):
                break

    def _drain(self) -> None:
        """Read and discard all available data from the PTY."""
        while True:
            try:
                os.read(self._master_fd, 4096)
            except (OSError, BlockingIOError):
                break

    async def _read_chunk(self) -> bytes:
        """Async read a chunk from the PTY master fd."""
        if getattr(self, "_abort_event", None) and self._abort_event.is_set():
            raise asyncio.CancelledError()

        if self._master_fd is None:
            raise asyncio.CancelledError()

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def _on_readable():
            if self._master_fd is None:
                if not future.done():
                    future.set_exception(asyncio.CancelledError())
                return

            try:
                loop.remove_reader(self._master_fd)
            except (ValueError, KeyError):
                pass

            try:
                data = os.read(self._master_fd, 4096)
                if not future.done():
                    future.set_result(data)
            except OSError as e:
                if not future.done():
                    future.set_exception(e)

        try:
            loop.add_reader(self._master_fd, _on_readable)
        except (ValueError, KeyError):
            raise asyncio.CancelledError()

        # We need to be able to abort this read if _abort_event is set
        try:
            return await future
        except asyncio.CancelledError:
            if self._master_fd is not None:
                try:
                    loop.remove_reader(self._master_fd)
                except (ValueError, KeyError):
                    pass
            raise

    async def execute(self, command: str, timeout: int = 300):
        """Execute a command and yield output chunks as they arrive."""
        async with self._lock:
            if not self.is_alive:
                await self.start()

            self._abort_event.clear()
            self._screen.reset()
            self._history_lines.clear()
            self._setup_history_callback()

            marker = f"__END_{uuid4().hex}__"

            # 1. Base64 encode the user command to avoid quote/escaping issues
            cmd_b64 = base64.b64encode(command.encode('utf-8')).decode('ascii')

            # 2. We use bash's 'read' and 'eval' to run this entirely invisibly.
            # We explicitly disable terminal echo while doing this setup,
            # run the command, then force echo back OFF when printing the marker
            # so the marker and technical commands don't show up.

            # Turn echo off so our setup isn't printed
            os.write(self._master_fd, b"stty -echo\n")
            await asyncio.sleep(0.1)
            self._drain() # throw away the command echo itself

            # We send the command and all post-command cleanup in a SINGLE line separated by semicolons.
            # This is CRITICAL. If we send multiple lines, bash leaves the subsequent lines in the TTY
            # input buffer while the user's command is running. Interactive apps (like claude, vim, etc.)
            # would then read those lines as user input! By sending it as one line, bash consumes it all
            # at once before the user's command starts.
            wrapped_cmd = (
                f"eval \"$(echo {cmd_b64} | base64 -d)\" ; "
                f"__ec=$? ; stty sane 2>/dev/null ; stty -echo 2>/dev/null ; PS1='' ; PS2='' ; echo '{marker}'$__ec\n"
            )
            os.write(self._master_fd, wrapped_cmd.encode())

            self._running_command = True
            raw_buffer = ""
            self.output_buffer = ""

            try:
                deadline = asyncio.get_event_loop().time() + timeout
                while True:
                    if self._abort_event.is_set():
                        yield "[COMMAND ABORTED BY SYSTEM]", True, None
                        return

                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        await self.cancel()
                        yield "[TIMED OUT after {}s]".format(timeout), True, None
                        return

                    try:
                        read_task = asyncio.create_task(self._read_chunk())
                        abort_task = asyncio.create_task(self._abort_event.wait())

                        done, pending = await asyncio.wait(
                            [read_task, abort_task],
                            timeout=min(remaining, 1.0),
                            return_when=asyncio.FIRST_COMPLETED
                        )

                        for t in pending:
                            t.cancel()

                        if abort_task in done:
                            yield "[COMMAND ABORTED BY /reset]", True, None
                            return

                        if read_task in done:
                            raw = read_task.result()
                        else:
                            # Timeout elapsed
                            if not self.is_alive:
                                if self.output_buffer:
                                    yield self.output_buffer, True, None
                                return
                            continue

                    except asyncio.CancelledError:
                        raise
                    except OSError:
                        if self.output_buffer:
                            yield self.output_buffer, True, None
                        return

                    text = raw.decode("utf-8", errors="replace")
                    raw_buffer += text

                    # Check for end marker in raw stream
                    marker_pattern = f"{marker}(\\d+)"
                    match = re.search(marker_pattern, raw_buffer)
                    if match:
                        exit_code = int(match.group(1))
                        # The marker might be split across lines or concatenated, get everything before the start of the marker
                        before_marker = raw_buffer[: match.start()]

                        # Just in case `stty -echo` failed or leaked, strip any visible internal commands from the very end
                        before_marker = re.sub(r'__ec=\$\?; stty sane.*?echo ".*?\$__ec"(\r?\n)?', '', before_marker, flags=re.DOTALL)

                        self._screen.reset()
                        self._history_lines.clear()
                        self._setup_history_callback()
                        self._stream.feed(before_marker)
                        rendered = self._render_screen()
                        self.output_buffer = rendered
                        self._running_command = False
                        yield rendered, True, exit_code
                        return

                    # Feed new data to virtual terminal and render
                    self._stream.feed(text)
                    rendered = self._render_screen()
                    self.output_buffer = rendered

                    if rendered:
                        yield rendered, False, None

            except asyncio.CancelledError:
                await self.cancel()
                raise
            finally:
                self._running_command = False

    async def send_input(self, text: str) -> None:
        """Send text as stdin to the running process."""
        if self._master_fd is not None:
            # Many TUI applications (like Claude Code) use React/Ink and ignore
            # keyboard shortcuts if multiple characters are received in a single chunk
            # (they treat it as a pasted string to prevent accidental actions).
            # We split the text and the Enter key (\r) with a tiny delay to simulate human typing.
            os.write(self._master_fd, text.encode("utf-8"))
            await asyncio.sleep(0.05)
            if self._master_fd is not None:
                os.write(self._master_fd, b"\r")

    async def send_raw(self, data: bytes) -> None:
        """Send raw bytes to PTY (for Ctrl+C etc.)."""
        if self._master_fd is not None:
            os.write(self._master_fd, data)

    async def cancel(self) -> None:
        """Cancel the currently running command."""
        if self._process and self.is_alive:
            try:
                os.killpg(self._process.pid, signal.SIGINT)
                await asyncio.sleep(2)
                if self.is_alive:
                    os.killpg(self._process.pid, signal.SIGTERM)
                    await asyncio.sleep(2)
                    if self.is_alive:
                        os.killpg(self._process.pid, signal.SIGKILL)
                        await self.reset()
                        return
            except ProcessLookupError:
                pass

        # Restore terminal state after cancel
        if self.is_alive:
            try:
                os.write(self._master_fd, b"stty sane\nstty -echo\nPS1=''\nPS2=''\n")
                await asyncio.sleep(0.2)
                self._drain()
            except OSError:
                pass
        self._running_command = False

    async def reset(self) -> None:
        """Kill the current bash process, abort readers, and start a fresh one."""
        self._abort_event.set()
        await self.close()
        await self.start()

    async def close(self) -> None:
        """Close the shell session."""
        self._abort_event.set()
        master_fd = self._master_fd
        self._master_fd = None  # Prevent further reads

        if self._process and self.is_alive:
            try:
                os.killpg(self._process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._process.wait()

        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass

        self._process = None
        self._running_command = False

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def is_busy(self) -> bool:
        return self._running_command
