# Telegram Terminal Bot

A full-featured remote Linux terminal inside Telegram. This is not just a simple command proxy — the bot runs a real **persistent PTY session** (pseudo-terminal), renders a virtual screen, and correctly handles interactive TUI applications (Claude Code, `vim`, `htop`, `nano`), streaming output, and real-time input.

## Features

- **Multiple sessions** — maintain several independent PTY sessions simultaneously, switch between them via inline buttons. Background sessions keep running.
- **Persistent session** — a single `bash` process lives between messages. `cd` works, environment variables and command history are preserved.
- **TUI support** — thanks to the built-in terminal emulator, interfaces like `claude`, `vim`, or `htop` render correctly. Cursor movements, screen clears, and alternate buffers work just like in a real terminal.
- **Interactive input** — if a running program awaits input (e.g., `y/n` or a dialog in Claude Code), any messages you send are forwarded to the process's `stdin`.
- **Streaming output** — for long-running commands, the bot automatically updates the Telegram message (respecting API rate limits), showing progress in real time.
- **Long output pagination** — if output exceeds Telegram's 4096-character limit, it is automatically split into multiple messages.
- **Single-user security** — access is strictly limited to one user by Telegram ID. All others are silently ignored at the middleware level (messages and callback buttons).

## Setup

**1. Clone the repository:**
```bash
git clone https://github.com/YOUR_USERNAME/telegram-terminal-bot.git
cd telegram-terminal-bot
```

**2. Create a virtual environment and install dependencies:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Configure environment variables:**
```bash
cp .env.example .env
```

Edit `.env`:
- `BOT_TOKEN` — your bot token from [@BotFather](https://t.me/BotFather)
- `AUTHORIZED_USER_ID` — your Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot))

**4. Run the bot:**
```bash
python run.py
```

> It is recommended to run the bot as a regular user (not root). For production use, consider setting up a `systemd` service or Docker container.

### systemd service (optional)

Create `/etc/systemd/system/telegram-terminal-bot.service`:

```ini
[Unit]
Description=Telegram Terminal Bot
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/path/to/telegram-terminal-bot
ExecStart=/path/to/telegram-terminal-bot/.venv/bin/python run.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable --now telegram-terminal-bot
```

## Usage

- **Send any command** (e.g., `ls -la`, `pwd`, `claude`) — it will execute in the terminal.
- While a command is running, any new text messages are forwarded to the running process as input.
- `/cancel` — gracefully cancel the current command (sends `SIGINT` → `SIGTERM` → `SIGKILL`).
- `/reset` — hard reset of the active session. The current `bash` process is killed and a fresh PTY is started. Use this if a session hangs completely.
- `/sessions` — show all sessions with inline buttons: switch, create new, or delete.
- `/new <name>` — create a new named session and switch to it immediately.
- `/help` — short usage reference.

### Working with multiple sessions

While one session is busy (e.g., running `claude` or a long command), you can switch to another:

1. Send `/sessions` — the bot shows the session list with buttons.
2. Tap a session — the active session changes.
3. Your commands now go to the new session; the background one keeps running.

Any plain text sent while the active session is busy is forwarded as `stdin` to the running process (dialog answers, vim input, etc.).

## Architecture

Building a proper Telegram ↔ TTY bridge requires solving several non-obvious problems. Here is how they are handled:

### 1. Virtual terminal emulator (`pyte`)
TUI programs send ANSI escape sequences not just for color, but for cursor control (`move cursor 5 lines up`, `clear screen`). Simply concatenating and sending raw PTY output to Telegram would turn TUI application interfaces into a garbled mess of control characters.

**Solution:** All PTY output is fed through a `pyte.Screen` virtual terminal (120×40). The bot takes a "screenshot" of this text screen (`_render_screen`) and sends that clean, properly rendered text to Telegram. Lines that scroll off the top of the terminal are captured and stored in a scroll history buffer.

### 2. Hidden execution and end markers
To detect when a command has finished, the bot sends a unique UUID marker after command execution.

**Problem:** If sent as `command; echo "MARKER"`, both the command line and marker may be echoed on the virtual terminal screen, appearing in Telegram output or mixing with interactive command output.

**Solution:**
- The original command is base64-encoded to avoid quoting/escaping issues (`eval "$(echo <b64> | base64 -d)"`).
- Before printing the marker, terminal input echo is disabled (`stty -echo`).
- The entire chain — "execute → restore terminal (`stty sane`) → print marker" — is sent as a **single line** separated by `;`. This prevents TUI applications from reading the housekeeping commands from the PTY input buffer before they finish.

### 3. Interactive input (Enter problem)
When forwarding text to an interactive application via `send_input`, a plain `\n` (Line Feed) is interpreted by the PTY as a cursor-down movement, not as Enter confirmation.

**Solution:** Input is sent with an explicit `\r` (Carriage Return) appended, which Linux PTY correctly interprets as the Enter key.

### 4. Background polling and Telegram rate limits
A long-running command may produce output in parts or be silent for a while.

**Solution:** The PTY reading process (`shell.py`) and the message update process (`sender.py`) are decoupled asynchronously. `shell` continuously renders the virtual screen into an in-memory buffer. `sender` runs a background task that every `2.0` seconds reads a screen snapshot and calls `edit_text` on the Telegram message if it changed. This creates a smooth "live output" feel while protecting against Telegram API flood limits.

## Stack

- Python 3.12+
- [aiogram 3.x](https://github.com/aiogram/aiogram)
- [pyte](https://github.com/selectel/pyte)
- Standard library: `pty`, `asyncio`, `subprocess`

## License

MIT
