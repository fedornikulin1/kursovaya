#!/usr/bin/env bash
set -o errexit
python -m pip install -r requirements.lock.txt
python manage.py collectstatic --noinput
