#!/bin/bash
# Exit on error
set -o errexit

# Install system dependencies
apt-get update
apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    binutils \
    libproj-dev \
    python3-dev \
    build-essential

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install Python packages
pip install -r requirements.txt

# Django commands
python manage.py collectstatic --noinput
python manage.py migrate