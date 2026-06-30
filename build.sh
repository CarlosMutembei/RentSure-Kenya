#!/usr/bin/env bash
# exit on error
set -o errexit

# Upgrade installer tools
pip install --upgrade pip setuptools wheel

# Install dependencies using your requirements.txt
pip install -r requirements.txt

# Run core django preparation commands
python manage.py collectstatic --noinput
python manage.py migrate