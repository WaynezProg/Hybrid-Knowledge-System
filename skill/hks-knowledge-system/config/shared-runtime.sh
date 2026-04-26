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
export KS_ROOT="${KS_ROOT:-$HKS_REPO_ROOT/.hks-runs/work/ks}"
export HKS_WORKSPACE_REGISTRY="${HKS_WORKSPACE_REGISTRY:-$HKS_REPO_ROOT/.hks-runs/workspaces.json}"

mkdir -p "$(dirname "$KS_ROOT")" "$(dirname "$HKS_WORKSPACE_REGISTRY")"

printf 'HKS_REPO_ROOT=%s\n' "$HKS_REPO_ROOT"
printf 'KS_ROOT=%s\n' "$KS_ROOT"
printf 'HKS_WORKSPACE_REGISTRY=%s\n' "$HKS_WORKSPACE_REGISTRY"
