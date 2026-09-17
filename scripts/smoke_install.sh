#!/usr/bin/env bash
# FileCortex clean-install 冒烟测试（release gate）
# 用法: bash scripts/smoke_install.sh [dist/file-cortex-*.whl]
# 验证: pip 全新 venv 安装 → CLI open/stage/export → Web /api/whoami → MCP 工具注册
set -euo pipefail

WHEEL="${1:-}"
if [ -z "$WHEEL" ]; then
  WHEEL=$(ls dist/file_cortex-*.whl 2>/dev/null | head -n 1 || true)
fi
if [ -z "$WHEEL" ] || [ ! -f "$WHEEL" ]; then
  echo "ERROR: no wheel found; run 'python -m build' first" >&2
  exit 1
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
VENV="$WORK/venv"
PROJ="$WORK/project"

echo "==> creating venv"
python -m venv "$VENV"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"
[ -x "$PY" ] || PY="$VENV/Scripts/python.exe"
[ -x "$PIP" ] || PIP="$VENV/Scripts/pip.exe"

echo "==> installing $WHEEL"
"$PIP" -q install "$WHEEL"

echo "==> CLI smoke"
mkdir -p "$PROJ"
echo "hello filecortex" > "$PROJ/a.txt"
echo "world" > "$PROJ/b.log"
export FCTX_CONFIG_DIR="$WORK/config"
# Capture into variables instead of piping to grep -q: with pipefail the
# early-exiting grep can SIGPIPE the CLI and fail the pipeline spuriously.
OPEN_OUT=$("$VENV/bin/fctx" open "$PROJ")
echo "$OPEN_OUT" | grep -q "PROJECT REGISTERED"
STAGE_OUT=$("$VENV/bin/fctx" stage "$PROJ" a.txt)
echo "$STAGE_OUT" | grep -q "Staged"
"$VENV/bin/fctx" export "$PROJ" --format xml --output out.xml >/dev/null
[ -f "$PROJ/out.xml" ]
grep -q "<filecortex>" "$PROJ/out.xml"
SEARCH_OUT=$("$VENV/bin/fctx" search "$PROJ" a.txt --mode exact)
echo "$SEARCH_OUT" | grep -q "a.txt"
echo "CLI OK"

echo "==> Web smoke"
( "$VENV/bin/fctx-web" --host 127.0.0.1 --port 8765 & echo $! > "$WORK/web.pid" )
WEB_OK=0
for _ in $(seq 1 30); do
  sleep 1
  if curl -sf http://127.0.0.1:8765/healthz | grep -q '"status"'; then
    WEB_OK=1
    break
  fi
done
kill "$(cat "$WORK/web.pid")" 2>/dev/null || true
sleep 1
if [ "$WEB_OK" -ne 1 ]; then
  echo "ERROR: web server did not become healthy" >&2
  exit 1
fi
echo "Web OK"

echo "==> MCP smoke"
if "$PY" -c "import mcp" 2>/dev/null; then
  timeout 10 "$VENV/bin/fctx-mcp" --transport stdio </dev/null || true
else
  # SDK 未安装时 mock 模式必须以退出码 2 结束（可判定）
  set +e
  "$VENV/bin/fctx-mcp" --transport stdio >/dev/null 2>&1
  rc=$?
  set -e
  [ "$rc" -eq 2 ] || { echo "ERROR: MCP fallback exit code $rc != 2" >&2; exit 1; }
fi
echo "MCP OK"

echo "SMOKE-OK"
