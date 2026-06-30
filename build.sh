#!/bin/bash

echo "🚀 Starting RentSure Kenya build..."

# Install system dependencies for GDAL/GeoDjango
echo "📦 Installing GDAL and system dependencies..."
apt-get update && apt-get install -y \
    binutils \
    libproj-dev \
    gdal-bin \
    libgdal-dev \
    python3-dev \
    build-essential

# Set GDAL environment variables
export GDAL_LIBRARY_PATH=/usr/lib/libgdal.so
export GDAL_DATA=/usr/share/gdal
export PROJ_LIB=/usr/share/proj

# Install Python dependencies
echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# Run Django commands
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

echo "🗄️ Running migrations..."
python manage.py migrate

echo "✅ Build complete!"