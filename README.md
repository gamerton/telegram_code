# Telegram Terminal Bot

[English](#english) | [Русский](#русский)

---

## English

A full-featured remote Linux terminal inside Telegram. This is not just a simple command proxy — the bot runs a real **persistent PTY session** (pseudo-terminal), renders a virtual screen, and correctly handles interactive TUI applications (Claude Code, `vim`, `htop`, `nano`), streaming output, and real-time input.

### Features

- **Multiple sessions** — maintain several independent PTY sessions simultaneously, switch between them via inline buttons. Background sessions keep running.
- **Persistent session** — a single `bash` process lives between messages. `cd` works, environment variables and command history are preserved.
- **TUI support** — thanks to the built-in terminal emulator, interfaces like `claude`, `vim`, or `htop` render correctly. Cursor movements, screen clears, and alternate buffers work just like in a real terminal.
- **Interactive input** — if a running program awaits input (e.g., `y/n` or a dialog in Claude Code), any messages you send are forwarded to the process's `stdin`.
- **Streaming output** — for long-running commands, the bot automatically updates the Telegram message (respecting API rate limits), showing progress in real time.
- **Long output pagination** — if output exceeds Telegram's 4096-character limit, it is automatically split into multiple messages.
- **Single-user security** — access is strictly limited to one user by Telegram ID. All others are silently ignored at the middleware level.

### Setup

**1. Clone the repository:**
```bash
git clone https://github.com/gamerton/telegram-terminal-bot.git
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

#### systemd service (optional)

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

### Usage

- **Send any command** (e.g., `ls -la`, `pwd`, `claude`) — it will execute in the terminal.
- While a command is running, any new text messages are forwarded to the running process as input.
- `/cancel` — gracefully cancel the current command (sends `SIGINT` → `SIGTERM` → `SIGKILL`).
- `/reset` — hard reset of the active session. Kills the current `bash` process and starts a fresh PTY.
- `/sessions` — show all sessions with inline buttons: switch, create new, or delete.
- `/new <name>` — create a new named session and switch to it immediately.
- `/help` — short usage reference.

#### Working with multiple sessions

While one session is busy (e.g., running `claude` or a long command), you can switch to another:

1. Send `/sessions` — the bot shows the session list with buttons.
2. Tap a session — the active session changes.
3. Your commands now go to the new session; the background one keeps running.

Any plain text sent while the active session is busy is forwarded as `stdin` to the running process.

### Architecture

#### 1. Virtual terminal emulator (`pyte`)
TUI programs send ANSI escape sequences not just for color, but for cursor control. Simply sending raw PTY output to Telegram would produce garbled text.

**Solution:** All PTY output is fed through a `pyte.Screen` virtual terminal (120×40). The bot renders a clean "screenshot" of this screen and sends it to Telegram. Lines that scroll off the top are captured in a history buffer.

#### 2. Hidden execution and end markers
To detect command completion, the bot sends a unique UUID marker after execution.

**Solution:** The command is base64-encoded to avoid escaping issues. Terminal echo is disabled before printing the marker. The entire chain (execute → restore terminal → print marker) is sent as a **single line** via `;`, preventing TUI apps from reading housekeeping commands from the PTY buffer.

#### 3. Interactive input (Enter problem)
A plain `\n` is interpreted by PTY as cursor-down, not Enter.

**Solution:** Input is sent with an explicit `\r` (Carriage Return) appended.

#### 4. Background polling and rate limits
PTY reading (`shell.py`) and message updating (`sender.py`) are decoupled asynchronously. `shell` continuously renders the screen to an in-memory buffer. `sender` polls it every 2 seconds and calls `edit_text` only when content changes.

### Stack

- Python 3.12+
- [aiogram 3.x](https://github.com/aiogram/aiogram)
- [pyte](https://github.com/selectel/pyte)
- Standard library: `pty`, `asyncio`, `subprocess`

---

## Русский

Полноценный удалённый Linux-терминал прямо в Telegram. Это не просто скрипт для проксирования команд — бот поднимает настоящую **persistent PTY-сессию** (pseudo-terminal), разворачивает виртуальный экран и корректно поддерживает интерактивные TUI-приложения (Claude Code, `vim`, `htop`, `nano`), потоковый вывод и ввод данных в реальном времени.

### Возможности

- **Множество сессий** — несколько независимых PTY-сессий одновременно, переключение через inline-кнопки. Фоновые сессии продолжают работать.
- **Persistent сессия** — один процесс `bash` живёт между отправками сообщений. Работает `cd`, сохраняются переменные окружения и история команд.
- **Поддержка TUI** — благодаря встроенному эмулятору терминала, интерфейсы `claude`, `vim` или `htop` отображаются корректно. Перемещения курсора, очистка экрана и альтернативные буферы отрабатываются как в настоящем терминале.
- **Интерактивный ввод** — если запущенная программа ждёт ввод (например, ответ `y/n` или диалог в Claude Code), любые отправленные сообщения перенаправляются в `stdin` процесса.
- **Потоковое обновление** — для долгих команд бот автоматически обновляет сообщение в Telegram (с учётом rate limits API), показывая процесс в реальном времени.
- **Пагинация длинного вывода** — если вывод превышает лимит Telegram (4096 символов), он автоматически бьётся на несколько сообщений.
- **Безопасность** — доступ строго ограничен одному пользователю по Telegram ID. Все остальные игнорируются на уровне middleware.

### Установка

**1. Клонируйте репозиторий:**
```bash
git clone https://github.com/gamerton/telegram-terminal-bot.git
cd telegram-terminal-bot
```

**2. Создайте виртуальное окружение и установите зависимости:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Настройте переменные окружения:**
```bash
cp .env.example .env
```

Отредактируйте `.env`:
- `BOT_TOKEN` — токен вашего бота от [@BotFather](https://t.me/BotFather)
- `AUTHORIZED_USER_ID` — ваш Telegram ID (узнать у [@userinfobot](https://t.me/userinfobot))

**4. Запустите бота:**
```bash
python run.py
```

> Рекомендуется запускать бота под обычным пользователем (не root). Для продакшна настройте systemd-сервис или Docker-контейнер.

#### systemd-сервис (опционально)

Создайте `/etc/systemd/system/telegram-terminal-bot.service`:

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

Затем:
```bash
sudo systemctl enable --now telegram-terminal-bot
```

### Использование

- **Напишите любую команду** (например, `ls -la`, `pwd`, `claude`) — она выполнится в терминале.
- Во время работы команды любые новые сообщения отправляются запущенному процессу как ввод.
- `/cancel` — мягкая отмена команды (последовательно: `SIGINT` → `SIGTERM` → `SIGKILL`).
- `/reset` — жёсткий сброс активной сессии. Текущий `bash` убивается, поднимается новый PTY.
- `/sessions` — список всех сессий с inline-кнопками: переключиться, создать, удалить.
- `/new <name>` — создать новую сессию с именем и сразу переключиться на неё.
- `/help` — краткая справка.

#### Работа с несколькими сессиями

Пока одна сессия занята (например, в ней запущен `claude`), можно переключиться на другую:

1. Напишите `/sessions` — бот покажет список сессий с кнопками.
2. Нажмите на нужную сессию — активная сессия сменится.
3. Теперь ваши команды идут в новую сессию, а фоновая продолжает работать.

Обычный текст, пока активная сессия занята, отправляется как `stdin` запущенному процессу.

### Архитектура

#### 1. Виртуальный эмулятор терминала (`pyte`)
TUI-программы отправляют ANSI-escape-последовательности для управления курсором и экраном. Просто конкатенировать и слать сырой вывод в Telegram нельзя — получится каша символов.

**Решение:** Весь вывод прогоняется через виртуальный экран `pyte.Screen` (120×40). Бот делает «скриншот» текстового экрана и отправляет чистый текст в Telegram. Строки, выходящие за верхний край терминала, перехватываются и сохраняются в историю прокрутки.

#### 2. Скрытое выполнение и система маркеров
Для определения завершения команды бот отправляет уникальный UUID-маркер после её выполнения.

**Решение:** Команда кодируется в base64, чтобы избежать проблем с экранированием. Перед печатью маркера отключается echo (`stty -echo`). Вся цепочка «выполнение → restore → маркер» посылается **одной строкой** через `;`, что не позволяет TUI-приложениям перехватить служебные команды из буфера PTY.

#### 3. Интерактивный ввод (проблема Enter)
Обычный символ `\n` воспринимается PTY как перемещение курсора вниз, а не как нажатие Enter.

**Решение:** Ввод пересылается с добавлением символа `\r` (Carriage Return), который PTY корректно интерпретирует как Enter.

#### 4. Фоновый polling и rate limits
Чтение PTY (`shell.py`) и обновление сообщения (`sender.py`) асинхронно развязаны. `shell` непрерывно рендерит экран в буфер в памяти. `sender` раз в 2 секунды забирает слепок и вызывает `edit_text`, если содержимое изменилось.

### Стек

- Python 3.12+
- [aiogram 3.x](https://github.com/aiogram/aiogram)
- [pyte](https://github.com/selectel/pyte)
- Стандартная библиотека: `pty`, `asyncio`, `subprocess`

---

## Support / Поддержать

If you find this project useful, you can support the author:

**[Поддержать на Boosty](https://boosty.to/gamerton/donate)**

---

## License / Лицензия

MIT
