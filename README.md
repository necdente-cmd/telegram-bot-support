# OZ Support Telegram Bot

Production-oriented rewrite of the in-group support assistant: keyword tips, help-phrase escalation, optional AI (`/ask`), and admin tools.

## Security

- **Do not put `BOT_TOKEN` in source code.** Use `.env` (see `.env.example`).
- If a token was ever pasted into a chat or committed, **revoke it in @BotFather** (`/revoke`) and issue a new one. The previous token must be treated as public.

## Setup

```text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `BOT_TOKEN`, `GROUP_CHAT_ID`, and `ADMIN_IDS` in `.env`. Optional: `DEEPSEEK_API_KEY`.

### Database migrations (Alembic)

The bot applies migrations to **head** on startup. You can also run them yourself:

```text
alembic upgrade head
alembic revision --autogenerate -m "describe change"
alembic downgrade -1
```

Default data (keywords, a responsible username) is seeded only when tables are empty.

### Run

```text
python -m bot
```

Logs go to stdout and to `logs/bot.log` with size-based rotation (`LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`). `LOG_LEVEL` accepts `DEBUG`, `INFO`, `WARNING`, `ERROR`.

## 24/7 on Railway ([railway.com](https://railway.com))

The bot talks to Telegram with **long polling**. It does not need a public website or webhook. Railway just has to keep `python -m bot` running.

1. Stop any local copy of the bot (two processes with the same `BOT_TOKEN` fight over updates).
2. Put this repo on GitHub (or upload the project files into the Railway service).
3. In the Railway service open **Variables** and set at least:

   | Variable | Example |
   | --- | --- |
   | `BOT_TOKEN` | new token from @BotFather |
   | `GROUP_CHAT_ID` | `-100…` of the support group |
   | `ADMIN_IDS` | your Telegram numeric id |
   | `BOT_USERNAME` | `oz_support_bot` |
   | `DEEPSEEK_API_KEY` | optional |

   Do **not** rely on a `.env` file on Railway. Variables in the dashboard override it.
4. **Settings → Deploy**: start command must be `python -m bot` (already in `railway.toml` / `Procfile`).
5. Deploy. In **Logs** you should see `Starting support bot` and Alembic `Running upgrade`.
6. In Telegram send `/help` to the bot. It should answer.

SQLite on Railway is wiped on every redeploy unless you attach a **Volume** (for example mount `/data` and set `DATABASE_URL=sqlite:////data/support.db`). PostgreSQL from Railway also works: paste its URL into `DATABASE_URL`.

## Dynamic command reload

Slash-commands are declared in `commands.yaml`. After editing that file or handler modules, an admin can send:

```text
/reload_commands
```

Handlers are dropped and re-imported; the process is not restarted. Message and callback handlers stay loaded until a full restart.

## Layout

```text
bot/config.py              settings from the environment
bot/logging_setup.py       rotating file + console logging
bot/db/                    SQLAlchemy models, engine, repository
bot/domain/matching.py     keyword / help / “about the bot” logic
bot/services/              AI, group notifications, command registry
bot/handlers/              Telegram handlers
alembic/versions/          schema migrations
commands.yaml              slash-command map
```

## Commands

Public: `/help`, `/ask`, `/list_keywords`, `/list_responsible`

Admin: `/add_keyword`, `/remove_keyword`, `/add_responsible`, `/remove_responsible`, `/ban_user`, `/unban_user`, `/list_banned`, `/reload_commands`
