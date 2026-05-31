#!/bin/bash
set -euo pipefail
export LD_LIBRARY_PATH="$(python3 -c 'from core.cuda_runtime import cuda_library_path_export; print(cuda_library_path_export())')${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$@"
