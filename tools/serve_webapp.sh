#!/usr/bin/env bash
# Run the local web workbench in the background (Linux / macOS).
#
# Usage:
#   bash tools/serve_webapp.sh start   [--host 0.0.0.0] [--port 5000]
#   bash tools/serve_webapp.sh stop    [--port 5000]
#   bash tools/serve_webapp.sh restart [--host 0.0.0.0] [--port 5000]
#   bash tools/serve_webapp.sh status  [--port 5000]
#
# start detaches "python webapp/app.py" with nohup, records its pid in
# logs/webapp.pid, appends its output to logs/webapp.log and waits for the
# front page to answer HTTP 200 before reporting success (the first start on a
# network share can take over a minute).
#
# stop ends the recorded process and also whatever else currently listens on
# the port, because a manually started instance has no pid file; without that,
# the next start would fail with "address already in use" while the old code
# kept serving.
#
# The interpreter is $PYTHON when set, otherwise .venv/bin/python when present,
# otherwise python3. logs/ is gitignored. One instance per checkout: the pid
# file and the log are shared by every port.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
cd "$ROOT" || exit 1

PID_FILE="logs/webapp.pid"
LOG_FILE="logs/webapp.log"
HOST="0.0.0.0"
PORT="5000"
WAIT_SECONDS="${WEBAPP_WAIT_SECONDS:-120}"

usage() {
  cat >&2 <<'USAGE'
usage: bash tools/serve_webapp.sh {start|stop|restart|status} [--host H] [--port N]

  start    background the web workbench and wait for HTTP 200 (default)
  stop     end it, and anything else listening on the port
  restart  stop, then start
  status   pid file, listening pids, HTTP code and log path

Environment:
  PYTHON               interpreter to use (default: .venv/bin/python, else python3)
  WEBAPP_WAIT_SECONDS  seconds to wait for HTTP 200 on start (default 120)
USAGE
  exit 2
}

action="${1:-}"
if [ -z "$action" ]; then
  usage
fi
shift

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) HOST="${2:-}"; shift 2 ;;
    --port) PORT="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown option: $1" >&2; usage ;;
  esac
done
case "$PORT" in
  ''|*[!0-9]*) echo "bad port: ${PORT}" >&2; exit 2 ;;
esac

# ---------- helpers ----------

pick_python() {
  if [ -n "${PYTHON:-}" ]; then
    printf '%s\n' "$PYTHON"
    return 0
  fi
  if [ -x ".venv/bin/python" ]; then
    printf '%s\n' ".venv/bin/python"
    return 0
  fi
  command -v python3 2>/dev/null || command -v python 2>/dev/null
}

# Print the pid recorded by a previous start, but only while it is still alive.
recorded_pid() {
  local pid
  [ -f "$PID_FILE" ] || return 1
  pid="$(tr -dc '0-9' < "$PID_FILE")"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  printf '%s\n' "$pid"
}

# Print the pids of every process listening on $PORT (needs ss or lsof).
port_pids() {
  local listing
  if command -v ss >/dev/null 2>&1; then
    listing="$(ss -ltnp 2>/dev/null | awk -v port="$PORT" -F'[ \t]+' \
      '{ n = split($4, a, ":"); if (a[n] == port) print $0 }')"
    printf '%s\n' "$listing" | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u
    return 0
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u
  fi
  return 0
}

http_code() {
  local code="000"
  if command -v curl >/dev/null 2>&1; then
    code="$(curl -s -o /dev/null -m 3 -w '%{http_code}' \
      "http://127.0.0.1:${PORT}/" 2>/dev/null)" || code="000"
  fi
  printf '%s\n' "${code:-000}"
}

describe_pids() {
  local pid
  for pid in $(port_pids); do
    printf '  pid %s: %s\n' "$pid" "$(ps -o args= -p "$pid" 2>/dev/null || echo '?')"
  done
}

# ---------- commands ----------

do_start() {
  mkdir -p logs
  local pid py busy waited code
  pid="$(recorded_pid || true)"
  if [ -n "$pid" ]; then
    echo "already running (pid ${pid}); use restart to replace it"
    return 0
  fi
  rm -f "$PID_FILE"
  busy="$(port_pids)"
  if [ -n "$busy" ]; then
    echo "port ${PORT} is already in use:" >&2
    describe_pids >&2
    echo "run 'bash tools/serve_webapp.sh stop --port ${PORT}' first" >&2
    return 1
  fi
  py="$(pick_python)"
  if [ -z "$py" ]; then
    echo "no python3 found; set PYTHON=/path/to/python" >&2
    return 1
  fi
  echo "==> starting webapp on ${HOST}:${PORT} with ${py}"
  nohup "$py" webapp/app.py --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"

  waited=0
  code=""
  while [ "$waited" -lt "$WAIT_SECONDS" ]; do
    code="$(http_code)"
    [ "$code" = "200" ] && break
    sleep 1
    waited=$((waited + 1))
  done
  if [ "$code" != "200" ]; then
    echo "no HTTP 200 after ${WAIT_SECONDS}s (last code ${code}); last log lines:" >&2
    tail -n 5 "$LOG_FILE" >&2
    return 1
  fi
  echo "==> http://${HOST}:${PORT}/ answers 200 (pid $(tr -dc '0-9' < "$PID_FILE"), log ${LOG_FILE})"
}

do_stop() {
  local pid pids p remaining waited
  pid="$(recorded_pid || true)"
  pids="$(printf '%s\n%s\n' "$pid" "$(port_pids)" | grep -v '^$' | sort -u | tr '\n' ' ')"
  pids="${pids% }"
  if [ -z "$pids" ]; then
    echo "not running: no live pid file and nothing listens on port ${PORT}"
    rm -f "$PID_FILE"
    return 0
  fi
  echo "==> stopping pid(s): ${pids}"
  for p in $pids; do
    kill "$p" 2>/dev/null || true
  done

  remaining=""
  waited=0
  while [ "$waited" -lt 15 ]; do
    remaining="$(port_pids | tr '\n' ' ')"
    remaining="${remaining% }"
    if [ -z "$remaining" ]; then
      break
    fi
    sleep 1
    waited=$((waited + 1))
  done
  if [ -n "$remaining" ]; then
    echo "  still listening after 15s, sending SIGKILL to ${remaining}"
    for p in $remaining; do
      kill -9 "$p" 2>/dev/null || true
    done
    sleep 1
  fi
  rm -f "$PID_FILE"
  if [ -n "$(port_pids)" ]; then
    echo "port ${PORT} is still in use (another user's process?)" >&2
    return 1
  fi
  echo "==> stopped; port ${PORT} is free"
}

do_status() {
  local pid lines
  pid="$(recorded_pid || true)"
  lines=""
  if [ -f "$LOG_FILE" ]; then
    lines=" ($(wc -l < "$LOG_FILE") lines)"
  fi
  printf 'pid file     : %s\n' "$PID_FILE"
  printf 'recorded pid : %s\n' "${pid:-none}"
  printf 'listening    : %s\n' "$(port_pids | tr '\n' ' ' | sed 's/ $//')"
  printf 'http code    : %s\n' "$(http_code)"
  printf 'log          : %s%s\n' "$LOG_FILE" "$lines"
  describe_pids
}

case "$action" in
  start) do_start ;;
  stop) do_stop ;;
  restart) do_stop && do_start ;;
  status) do_status ;;
  *) usage ;;
esac
