#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

# Copy videos manually since collectstatic may skip large binary files
mkdir -p staticfiles/videos
cp -r static/videos/*.mp4 staticfiles/videos/ 2>/dev/null || true

python manage.py migrate
