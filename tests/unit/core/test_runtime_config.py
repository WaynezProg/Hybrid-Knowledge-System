from __future__ import annotations

import json
from pathlib import Path

import pytest

from hks.core.config import config_value, shell_exports


@pytest.fixture()
def isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    env_path = tmp_path / "missing.env"
    yaml_path = tmp_path / "hks.yaml"
    monkeypatch.setenv("HKS_CONFIG_ENV", str(env_path))
    monkeypatch.setenv("HKS_CONFIG_FILE", str(yaml_path))
    for name in (
        "KS_ROOT",
        "HKS_WORKSPACE_REGISTRY",
        "HKS_EMBEDDING_MODEL",
        "HKS_OPENAI_API_KEY",
        "HKS_OPENAI_EMBEDDING_DIMENSIONS",
        "HKS_OFFICE_TIMEOUT_SEC",
        "HKS_LLM_NETWORK_OPT_IN",
        "HKS_LLM_PROVIDER_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    return yaml_path


@pytest.mark.unit
def test_config_value_reads_yaml_values(isolated_config: Path) -> None:
    isolated_config.write_text(
        """
runtime:
  ks_root: "${HKS_REPO_ROOT}/.hks-runs/openai/ks"
  workspace_registry: "${HKS_REPO_ROOT}/.hks-runs/workspaces.json"
embedding:
  model: "openai:text-embedding-3-small"
  openai:
    api_key: "yaml-key"
    dimensions: 256
ingest:
  office:
    timeout_sec: 45
llm:
  network_opt_in: true
  providers:
    openai:
      api_key: "llm-key"
""".strip(),
        encoding="utf-8",
    )

    assert config_value("KS_ROOT").endswith("/.hks-runs/openai/ks")
    assert config_value("HKS_WORKSPACE_REGISTRY").endswith("/.hks-runs/workspaces.json")
    assert config_value("HKS_EMBEDDING_MODEL") == "openai:text-embedding-3-small"
    assert config_value("HKS_OPENAI_API_KEY") == "yaml-key"
    assert config_value("HKS_OPENAI_EMBEDDING_DIMENSIONS") == "256"
    assert config_value("HKS_OFFICE_TIMEOUT_SEC") == "45"
    assert config_value("HKS_LLM_NETWORK_OPT_IN") == "1"
    assert config_value("HKS_LLM_PROVIDER_OPENAI_API_KEY") == "llm-key"


@pytest.mark.unit
def test_env_file_overrides_yaml(isolated_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = isolated_config.with_suffix(".env")
    isolated_config.write_text(
        "embedding:\n  model: openai:text-embedding-3-small\n",
        encoding="utf-8",
    )
    env_path.write_text("export HKS_EMBEDDING_MODEL=simple\n", encoding="utf-8")
    monkeypatch.setenv("HKS_CONFIG_ENV", str(env_path))

    assert config_value("HKS_EMBEDDING_MODEL") == "simple"


@pytest.mark.unit
def test_process_env_overrides_config_files(
    isolated_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated_config.write_text("embedding:\n  model: simple\n", encoding="utf-8")
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", "openai:text-embedding-3-small")

    assert config_value("HKS_EMBEDDING_MODEL") == "openai:text-embedding-3-small"


@pytest.mark.unit
def test_shell_exports_include_yaml_values(isolated_config: Path) -> None:
    isolated_config.write_text(
        """
runtime:
  ks_root: /tmp/hks-config-test/ks
embedding:
  model: simple
""".strip(),
        encoding="utf-8",
    )

    exports = shell_exports()

    assert "export KS_ROOT=/tmp/hks-config-test/ks" in exports
    assert "export HKS_EMBEDDING_MODEL=simple" in exports


@pytest.mark.unit
def test_config_value_reads_json_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "hks.json"
    json_path.write_text(
        json.dumps({"embedding": {"model": "simple"}, "writeback": {"auto_threshold": 0.5}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HKS_CONFIG_ENV", str(tmp_path / "missing.env"))
    monkeypatch.setenv("HKS_CONFIG_FILE", str(json_path))
    monkeypatch.delenv("HKS_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("HKS_WRITEBACK_AUTO_THRESHOLD", raising=False)

    assert config_value("HKS_EMBEDDING_MODEL") == "simple"
    assert config_value("HKS_WRITEBACK_AUTO_THRESHOLD") == "0.5"
