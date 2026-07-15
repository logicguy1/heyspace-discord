# heyspace-discord

Cog-based, single-guild Discord bot built on modern **discord.py** (slash commands),
**async SQLAlchemy 2.0** + **Alembic**, packaged with **Poetry** and run via **Docker Compose**
with PostgreSQL.

## Architecture

```
src/
├── main.py            # asyncio entrypoint
├── config.py          # typed settings (pydantic-settings / .env)
├── bot.py             # HeySpaceBot(commands.Bot): cog loader + guild command sync
├── lib/               # reusable branded classes
│   ├── embed.py       # Embed: color palette + footer = server icon
│   └── cog.py         # BaseCog: bot, logger, embed() + session() helpers
├── db/
│   ├── base.py        # Base, async engine, session factory
│   └── models/        # ORM models (imported so Alembic sees the metadata)
└── cogs/              # auto-loaded extensions (general.py -> /ping)
```

- **Single guild:** commands sync to `GUILD_ID` for instant registration (no ~1h global wait).
- **Branding:** `Embed` sets a timestamp, a palette color (`set_color("green")`, ...), and a footer
  whose icon is always the live server icon (`Embed.set_branding(guild)` on ready).
- **Migrations** run automatically on container start (`alembic upgrade head`).

## Run with Docker

```bash
cp .env.example .env      # fill DISCORD_TOKEN and GUILD_ID
docker compose up --build
```

Verify the schema:

```bash
docker compose exec db psql -U postgres -d heyspace -c "\dt"
```

Then run `/ping` in your guild.

## Local development

```bash
poetry install
cp .env.example .env      # point DATABASE_URL at localhost
alembic upgrade head
python -m src.main
```

### Creating a migration

```bash
alembic revision --autogenerate -m "describe change"
```

Add new models under `src/db/models/` and import them in `src/db/models/__init__.py` so Alembic
detects them.

### Adding a cog

Drop a `src/cogs/<name>.py` with a `class X(BaseCog)` and an `async def setup(bot)` — it loads
automatically on startup.
