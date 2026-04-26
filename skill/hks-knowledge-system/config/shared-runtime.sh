#!/usr/bin/env sh

# Source this file from any local agent session to use the same repo-local HKS
# runtime and workspace registry.
#
# Usage:
#   . skill/hks-knowledge-system/config/shared-runtime.sh

if command -v git >/dev/null 2>&1; then
  HKS_REPO_ROOT="${HKS_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
else
  HKS_REPO_ROOT="${HKS_REPO_ROOT:-$(pwd)}"
fi

export HKS_REPO_ROOT

HKS_CONFIG_ENV="${HKS_CONFIG_ENV:-$HKS_REPO_ROOT/config/hks.env}"
if [ -f "$HKS_CONFIG_ENV" ]; then
  # shellcheck disable=SC1090
  . "$HKS_CONFIG_ENV"
fi
export HKS_CONFIG_ENV

HKS_CONFIG_FILE="${HKS_CONFIG_FILE:-}"
export HKS_CONFIG_FILE
if command -v uv >/dev/null 2>&1 && { [ -f "$HKS_REPO_ROOT/config/hks.yaml" ] || [ -f "$HKS_REPO_ROOT/config/hks.json" ] || { [ -n "$HKS_CONFIG_FILE" ] && [ -f "$HKS_CONFIG_FILE" ]; }; }; then
  HKS_CONFIG_EXPORTS="$(
    cd "$HKS_REPO_ROOT" &&
      uv run python -m hks.core.config --shell 2>/dev/null
  )"
  if [ -n "$HKS_CONFIG_EXPORTS" ]; then
    eval "$HKS_CONFIG_EXPORTS"
  fi
fi

HKS_SHARED_RUNTIME_ENV="${HKS_SHARED_RUNTIME_ENV:-$HKS_REPO_ROOT/.hks-runs/shared-runtime.env}"
if [ -f "$HKS_SHARED_RUNTIME_ENV" ]; then
  # shellcheck disable=SC1090
  . "$HKS_SHARED_RUNTIME_ENV"
fi

export KS_ROOT="${KS_ROOT:-$HKS_REPO_ROOT/.hks-runs/work/ks}"
export HKS_WORKSPACE_REGISTRY="${HKS_WORKSPACE_REGISTRY:-$HKS_REPO_ROOT/.hks-runs/workspaces.json}"

mkdir -p "$(dirname "$KS_ROOT")" "$(dirname "$HKS_WORKSPACE_REGISTRY")"

printf 'HKS_REPO_ROOT=%s\n' "$HKS_REPO_ROOT"
printf 'HKS_CONFIG_ENV=%s\n' "$HKS_CONFIG_ENV"
printf 'HKS_CONFIG_FILE=%s\n' "$HKS_CONFIG_FILE"
printf 'HKS_SHARED_RUNTIME_ENV=%s\n' "$HKS_SHARED_RUNTIME_ENV"
printf 'KS_ROOT=%s\n' "$KS_ROOT"
printf 'HKS_WORKSPACE_REGISTRY=%s\n' "$HKS_WORKSPACE_REGISTRY"
