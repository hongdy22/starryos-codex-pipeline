#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

BIN_NAME="${CODEX_BIN_NAME:-codex-x86_64-unknown-linux-musl}"
TAR_PATH="${CODEX_TAR:-$SCRIPT_DIR/codex-x86_64-unknown-linux-musl.tar.gz}"
LOCAL_DIR="${CODEX_LOCAL_DIR:-$SCRIPT_DIR/.codex-local}"
BIN_DIR="$LOCAL_DIR/bin"
BIN_PATH="$BIN_DIR/$BIN_NAME"
CODEX_HOME_DIR="${CODEX_HOME:-$LOCAL_DIR/home}"
AUTH_SOURCE="${CODEX_AUTH_JSON:-$SCRIPT_DIR/auth.json}"
WORK_DIR="${CODEX_WORKDIR:-$SCRIPT_DIR}"
MODEL="${CODEX_MODEL:-gpt-5.5}"
REASONING_EFFORT="${CODEX_REASONING_EFFORT:-xhigh}"
SERVICE_TIER="${CODEX_SERVICE_TIER:-fast}"
FULL_ACCESS="${CODEX_FULL_ACCESS:-1}"

# Edit this line to change the default task run by `bash codex.sh`.
DEFAULT_PROMPT='请你新建一个 python 文件 hello.py，内容是输出 10 个 hello。'

usage() {
    cat <<'USAGE'
Usage:
  bash codex.sh
  bash codex.sh "请你新建一个 python 文件 hello.py，内容是输出 10 个 hello。"
  CODEX_PROMPT="请你新建一个 python 文件 hello.py，内容是输出 10 个 hello。" bash codex.sh

Optional environment variables:
  CODEX_PROMPT             Prompt to run when no command-line prompt is given.
  CODEX_WORKDIR            Workspace directory for Codex. Default: this script directory.
  CODEX_MODEL              Model name passed to Codex. Default: gpt-5.5.
  CODEX_SERVICE_TIER       Service tier passed to Codex. Default: fast.
  CODEX_REASONING_EFFORT   low | medium | high | xhigh. Default: xhigh.
  CODEX_FULL_ACCESS        1 to bypass approvals and sandbox. Default: 1.
  CODEX_SANDBOX            Used only when CODEX_FULL_ACCESS=0. Default: danger-full-access.
  CODEX_APPROVAL_POLICY    Used only when CODEX_FULL_ACCESS=0. Default: never.
  CODEX_AUTH_JSON          Path to auth.json. Default: ./auth.json.
  CODEX_TAR                Path to the Codex tar.gz. Default: ./codex-x86_64-unknown-linux-musl.tar.gz.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if [[ $# -gt 0 ]]; then
    PROMPT="$*"
else
    PROMPT="${CODEX_PROMPT:-$DEFAULT_PROMPT}"
fi

if [[ ! -x "$BIN_PATH" ]]; then
    if [[ ! -f "$TAR_PATH" ]]; then
        echo "Codex tarball not found: $TAR_PATH" >&2
        exit 1
    fi

    mkdir -p "$BIN_DIR"
    tar -xzf "$TAR_PATH" -C "$BIN_DIR"
    chmod +x "$BIN_PATH"
fi

if [[ ! -x "$BIN_PATH" ]]; then
    echo "Codex binary not found after extraction: $BIN_PATH" >&2
    exit 1
fi

if [[ ! -f "$AUTH_SOURCE" ]]; then
    echo "Codex auth file not found: $AUTH_SOURCE" >&2
    exit 1
fi

mkdir -p "$CODEX_HOME_DIR"
AUTH_DEST="$CODEX_HOME_DIR/auth.json"
if [[ "$AUTH_SOURCE" != "$AUTH_DEST" ]]; then
    install -m 600 "$AUTH_SOURCE" "$AUTH_DEST"
else
    chmod 600 "$AUTH_DEST"
fi

codex_args=(
    --model "$MODEL"
    -c "model_reasoning_effort=\"$REASONING_EFFORT\""
    -c "service_tier=\"$SERVICE_TIER\""
)

if [[ "$FULL_ACCESS" == "1" ]]; then
    codex_args+=(--dangerously-bypass-approvals-and-sandbox)
else
    codex_args+=(
        --ask-for-approval "${CODEX_APPROVAL_POLICY:-never}"
    )
fi

codex_args+=(
    exec
    --cd "$WORK_DIR"
    --color "${CODEX_COLOR:-auto}"
)

if [[ "$FULL_ACCESS" != "1" ]]; then
    codex_args+=(--sandbox "${CODEX_SANDBOX:-danger-full-access}")
fi

if [[ "${CODEX_EPHEMERAL:-1}" == "1" ]]; then
    codex_args+=(--ephemeral)
fi

codex_args+=("$PROMPT")

echo "Running Codex in: $WORK_DIR" >&2
echo "Model: $MODEL, service tier: $SERVICE_TIER, reasoning effort: $REASONING_EFFORT" >&2
if [[ "$FULL_ACCESS" == "1" ]]; then
    echo "Permission mode: full access, approvals and sandbox bypassed" >&2
else
    echo "Permission mode: sandbox=${CODEX_SANDBOX:-danger-full-access}, approval=${CODEX_APPROVAL_POLICY:-never}" >&2
fi
exec env CODEX_HOME="$CODEX_HOME_DIR" "$BIN_PATH" "${codex_args[@]}"
