#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies using Poetry (since the logs show you use Poetry)
poetry install

# Run Django commands
poetry run python manage.py collectstatic --no-input
poetry run python manage.py migrate