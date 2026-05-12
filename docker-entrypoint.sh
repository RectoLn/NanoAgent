#!/bin/sh
set -eu

APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"
APP_USER="${APP_USER:-nanoagent}"
APP_GROUP="${APP_GROUP:-nanoagent}"

export PYTHONDONTWRITEBYTECODE="${PYTHONDONTWRITEBYTECODE:-1}"

if [ "$(id -u)" = "0" ]; then
    if ! getent group "$APP_GID" >/dev/null 2>&1; then
        groupadd -g "$APP_GID" "$APP_GROUP"
    fi

    if ! getent passwd "$APP_UID" >/dev/null 2>&1; then
        useradd -u "$APP_UID" -g "$APP_GID" -M -s /usr/sbin/nologin "$APP_USER"
    fi

    mkdir -p /app/sessions /app/workspace/.tmp /app/workspace/skills /app/workspace/wiki /app/workspace/transcripts
    chown -R "$APP_UID:$APP_GID" \
        /app/sessions \
        /app/workspace/.tmp \
        /app/workspace/skills \
        /app/workspace/wiki \
        /app/workspace/transcripts

    exec gosu "$APP_UID:$APP_GID" "$@"
fi

exec "$@"
