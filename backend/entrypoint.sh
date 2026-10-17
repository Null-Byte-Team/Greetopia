#!/bin/sh
set -eu
# Persistent disks may be mounted with root ownership; make only the data mount writable
# before dropping privileges. The application itself runs as the unprivileged appuser.
mkdir -p /app/storage/photos
chown appuser:appuser /app/storage /app/storage/photos
exec gosu appuser uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-5000}" --workers 1
