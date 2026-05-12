#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

STAMP="$(date '+%Y-%m-%d')"
LOG_FILE="$LOG_DIR/dev-${STAMP}.log"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ui start ====="
} >>"$LOG_FILE"

CMD="FORCE_COLOR=1 CLICOLOR_FORCE=1 pnpm dev"

bash -lc "$CMD" 2>&1 \
  | while IFS= read -r line; do
      out="$(date '+%Y-%m-%d %H:%M:%S') $line"
      printf '%s\n' "$out"
      if [[ "${KEEP_ANSI_LOG:-0}" == "1" ]]; then
        printf '%s\n' "$out" >>"$LOG_FILE"
      else
        printf '%s\n' "$out" | perl -pe 's/\e\[[0-9;]*[mK]//g' >>"$LOG_FILE"
      fi
    done
