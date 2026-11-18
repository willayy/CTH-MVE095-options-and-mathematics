#!/bin/sh
set -e

if [ -d "/app/.git" ]; then
    echo "Updating repository from GitHub..."
    git -C /app pull origin main || true
else
    echo "Cloning repository from GitHub..."
    git clone --depth 1 https://github.com/willayy/CTH-MVE095-options-and-mathematics.git /app
fi

exec "$@"
