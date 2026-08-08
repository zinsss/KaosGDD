#!/bin/sh
set -eu

: "${APP_NAME:=Kaos Memos}"
: "${APP_MODE:=personal}"
: "${MEMOS_BASE_URL:=}"
: "${KAOSPRINT_URL:=}"
: "${DEFAULT_EDITOR_MODE:=markdown}"
: "${ALLOW_MARKDOWN_MODE:=true}"
: "${THEME:=nord}"

export APP_NAME APP_MODE MEMOS_BASE_URL KAOSPRINT_URL
export DEFAULT_EDITOR_MODE ALLOW_MARKDOWN_MODE THEME

envsubst \
  '${APP_NAME} ${APP_MODE} ${MEMOS_BASE_URL} ${KAOSPRINT_URL} ${DEFAULT_EDITOR_MODE} ${ALLOW_MARKDOWN_MODE} ${THEME}' \
  < /opt/kaos-memos/config.template.js \
  > /usr/share/nginx/html/config.js
