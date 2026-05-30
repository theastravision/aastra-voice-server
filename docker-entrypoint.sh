#!/bin/bash
set -euo pipefail
export LD_LIBRARY_PATH="$(python3 -c 'import os
try:
    import nvidia.cublas.lib as cublas_lib
    import nvidia.cudnn.lib as cudnn_lib
    print(os.path.dirname(cublas_lib.__file__) + ":" + os.path.dirname(cudnn_lib.__file__))
except ImportError:
    print(os.environ.get("LD_LIBRARY_PATH", ""))')${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$@"
