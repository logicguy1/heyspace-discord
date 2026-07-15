#!/usr/bin/env bash
set -euo pipefail

# Apply any pending database migrations, then launch the bot.
echo "Running database migrations..."
alembic upgrade head

echo "Starting bot..."
exec python -m src.main
