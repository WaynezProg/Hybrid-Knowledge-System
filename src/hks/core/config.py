"""Local configuration loader for HKS runtime tunables."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

ENV_CONFIG_ENV = "HKS_CONFIG_ENV"
ENV_CONFIG_FILE = "HKS_CONFIG_FILE"

_KNOWN_ENV_PATHS: dict[str, tuple[str, ...]] = {
    "KS_ROOT": ("runtime", "ks_root"),
    "HKS_WORKSPACE_REGISTRY": ("runtime", "workspace_registry"),
    "HKS_EMBEDDING_MODEL": ("embedding", "model"),
    "HKS_OPENAI_API_KEY": ("embedding", "openai", "api_key"),
    "OPENAI_API_KEY": ("embedding", "openai", "api_key"),
    "HKS_OPENAI_EMBEDDING_ENDPOINT": ("embedding", "openai", "endpoint"),
    "HKS_OPENAI_EMBEDDING_DIMENSIONS": ("embedding", "openai", "dimensions"),
    "HKS_OPENAI_TIMEOUT_SECONDS": ("embedding", "openai", "timeout_seconds"),
    "HKS_OPENAI_EMBEDDING_BATCH_SIZE": ("embedding", "openai", "batch_size"),
    "HKS_OPENAI_EMBEDDING_MAX_BATCH_TOKENS": (
        "embedding",
        "openai",
        "max_batch_tokens",
    ),
    "HKS_ROUTING_MODEL": ("routing", "model"),
    "HKS_ROUTING_RULES": ("routing", "rules_path"),
    "HKS_WRITEBACK_AUTO_THRESHOLD": ("writeback", "auto_threshold"),
    "HKS_MAX_FILE_MB": ("ingest", "max_file_mb"),
    "HKS_OFFICE_TIMEOUT_SEC": ("ingest", "office", "timeout_sec"),
    "HKS_OFFICE_MAX_FILE_MB": ("ingest", "office", "max_file_mb"),
    "HKS_IMAGE_TIMEOUT_SEC": ("ingest", "image", "timeout_sec"),
    "HKS_IMAGE_MAX_FILE_MB": ("ingest", "image", "max_file_mb"),
    "HKS_IMAGE_MAX_PIXELS": ("ingest", "image", "max_pixels"),
    "HKS_OCR_LANGS": ("ingest", "ocr", "langs"),
    "HKS_LLM_PROVIDER": ("llm", "provider"),
    "HKS_LLM_MODEL": ("llm", "model"),
    "HKS_LLM_NETWORK_OPT_IN": ("llm", "network_opt_in"),
}


def repo_root() -> Path:
    configured = os.environ.get("HKS_REPO_ROOT")
    if configured:
        return Path(configured).expanduser().resolve(strict=False)

    cwd = Path.cwd()
    for root in (cwd, *cwd.parents):
        if (root / "pyproject.toml").exists() and (root / "src" / "hks").is_dir():
            return root.resolve(strict=False)
    return cwd.resolve(strict=False)


def env_config_path() -> Path:
    configured = os.environ.get(ENV_CONFIG_ENV)
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    return repo_root() / "config" / "hks.env"


def structured_config_paths() -> tuple[Path, ...]:
    configured = os.environ.get(ENV_CONFIG_FILE)
    if configured:
        return (Path(configured).expanduser().resolve(strict=False),)

    root = repo_root()
    return (root / "config" / "hks.yaml", root / "config" / "hks.json")


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            parts = shlex.split(line, comments=True, posix=True)
        except ValueError:
            continue
        if not parts:
            continue
        if parts[0] == "export":
            parts = parts[1:]
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                values[key] = _expand_config_string(value)
    return values


def _yaml_loader() -> YAML:
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    return yaml


def _read_structured_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        payload = _yaml_loader().load(text)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def load_structured_config() -> dict[str, Any]:
    for path in structured_config_paths():
        if path.exists():
            return _read_structured_file(path)
    return {}


def _nested_get(payload: Mapping[str, Any], path: Iterable[str]) -> Any | None:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _coerce_config_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list | tuple):
        return "+".join(str(item) for item in value)
    return _expand_config_string(str(value))


def _expand_config_string(value: str) -> str:
    root = str(repo_root())
    expanded = value.replace("${HKS_REPO_ROOT}", root).replace("$HKS_REPO_ROOT", root)
    return os.path.expandvars(os.path.expanduser(expanded))


def _structured_value(name: str) -> str | None:
    payload = load_structured_config()
    if not payload:
        return None

    path = _KNOWN_ENV_PATHS.get(name)
    if path is not None:
        return _coerce_config_value(_nested_get(payload, path))

    match = re.fullmatch(r"HKS_LLM_PROVIDER_([A-Z0-9_]+)_(API_KEY|ENDPOINT)", name)
    if match:
        provider = match.group(1).lower().replace("_", "-")
        field = "api_key" if match.group(2) == "API_KEY" else "endpoint"
        return _coerce_config_value(_nested_get(payload, ("llm", "providers", provider, field)))

    return None


def config_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value not in (None, ""):
        return value

    env_value = _read_env_file(env_config_path()).get(name)
    if env_value not in (None, ""):
        return env_value

    return _structured_value(name)


def iter_config_exports() -> Iterable[tuple[str, str]]:
    names = set(_KNOWN_ENV_PATHS)
    payload = load_structured_config()
    providers = _nested_get(payload, ("llm", "providers"))
    if isinstance(providers, Mapping):
        for provider in providers:
            env_provider = str(provider).upper().replace("-", "_")
            names.add(f"HKS_LLM_PROVIDER_{env_provider}_API_KEY")
            names.add(f"HKS_LLM_PROVIDER_{env_provider}_ENDPOINT")

    for name in sorted(names):
        value = config_value(name)
        if value not in (None, ""):
            assert value is not None
            yield name, value


def shell_exports() -> str:
    lines = []
    for name, value in iter_config_exports():
        lines.append(f"export {name}={shlex.quote(value)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shell", action="store_true", help="Print shell export statements.")
    args = parser.parse_args()
    if args.shell:
        output = shell_exports()
        if output:
            print(output)


if __name__ == "__main__":
    main()
