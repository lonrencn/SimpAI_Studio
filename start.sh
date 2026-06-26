#!/bin/bash
# SimpAI Studio Linux Launch Script
# Usage: ./start.sh [GPU_ID] [extra args...]
# Example: ./start.sh 1
#          ./start.sh 3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GPU_ID="${1:-1}"
shift 2>/dev/null

MODELS_ROOT="${MODELS_ROOT:-$HOME/SimpleSDXL/models}"
USERHOME="${USERHOME:-users}"

# conda env
CONDA_ENV="${CONDA_ENV:-simpai}"
CONDA_PREFIX="$HOME/.conda/envs/$CONDA_ENV"

FRONTEND_PORT=9186
BACKEND_PORT=9187

# CUDA runtime libraries for onnxruntime-gpu etc.
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"

# ComfyUI backend CORS (set to * for full cross-origin API access)
export SIMPAI_COMFYD_CORS="*"

# External URL for reverse proxy (include port if non-standard)
# Set to empty string for local-only access
WEBROOT="${WEBROOT:-https://aigcn.daoson.work:8443}"

# ── 停掉旧进程 ──
# 1) 按命令行特征杀整个进程树（主进程 + ComfyUI 后端子进程）
pkill -f "entry_without_update" 2>/dev/null
# 2) 按端口兜底
for port in $FRONTEND_PORT $BACKEND_PORT; do
    pids=$(lsof -t -i :$port 2>/dev/null)
    [ -n "$pids" ] && kill $pids 2>/dev/null
done
sleep 2
# 3) 还没死就 SIGKILL
pkill -9 -f "entry_without_update" 2>/dev/null
for port in $FRONTEND_PORT $BACKEND_PORT; do
    pids=$(lsof -t -i :$port 2>/dev/null)
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null
done

# 4) 等端口真正释放（解决 TIME_WAIT / 子进程退出延迟）
for port in $FRONTEND_PORT $BACKEND_PORT; do
    for i in $(seq 1 30); do
        if ! lsof -i :$port >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    if lsof -i :$port >/dev/null 2>&1; then
        echo "WARNING: Port $port still in use after 30s, server may jump ports."
    fi
done

# 5) 进程都停了之后再清 DB 锁
DB_DIR="$SCRIPT_DIR/comfy/user"
if [ -d "$DB_DIR" ]; then
    rm -f "$DB_DIR"/comfyui.db-shm "$DB_DIR"/comfyui.db-wal "$DB_DIR"/comfyui.db.lock 2>/dev/null
fi

# 6) 确保 sageattention 兼容层 (.pth) 存在（conda 重建/pip 重装后会丢失）
PTH_FILE="$CONDA_PREFIX/lib/python3.13/site-packages/zz_sage_compat.pth"
if [ ! -f "$PTH_FILE" ]; then
    echo "import sys; sys.path.insert(0, '$SCRIPT_DIR'); from enhanced.sage_compat import apply as _sage_apply; _sage_apply()" > "$PTH_FILE"
    echo "Restored sageattention compat .pth"
fi

exec "$CONDA_PREFIX/bin/python" -u entry_without_update.py \
    --models-root "$MODELS_ROOT" \
    --userhome-path "$USERHOME" \
    --gpu-device-id "$GPU_ID" \
    --listen 0.0.0.0 \
    --port $FRONTEND_PORT \
    --backend-port $BACKEND_PORT \
    --webroot "$WEBROOT" \
    "$@"
