#!/usr/bin/env bash
# Safe .env loader — does not execute shell; handles values with spaces/Unicode.
# Usage: source scripts/load-env.sh && load_env_file .env

load_env_file() {
  local env_file="${1:-.env}"
  [[ -f "$env_file" ]] || return 0

  if ! command -v python3 >/dev/null 2>&1; then
    echo "load_env_file: python3 required to parse $env_file safely" >&2
    return 1
  fi

  eval "$(python3 - "$env_file" <<'PY'
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
for line in path.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if "=" not in stripped:
        continue
    key, _, val = stripped.partition("=")
    key = key.strip()
    if not key.replace("_", "").isalnum():
        continue
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        val = val[1:-1]
    print(f"export {key}={shlex.quote(val)}")
PY
)"
}
