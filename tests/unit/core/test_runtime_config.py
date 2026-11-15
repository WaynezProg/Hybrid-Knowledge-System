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
        "HKS_API_REQUIRE_TOKEN_FOR_READS",
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
api:
  require_token_for_reads: true
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
    assert config_value("HKS_API_REQUIRE_TOKEN_FOR_READS") == "1"
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


@pytest.fixture()
def user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key in (
        "HKS_CONFIG_FILE",
        "HKS_CONFIG_ENV",
        "HKS_REPO_ROOT",
        "KS_ROOT",
        "HKS_WORKSPACE_REGISTRY",
        "HKS_EMBEDDING_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    directory = tmp_path / "user-config" / "hks"
    directory.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(directory.parent))
    cwd = tmp_path / "unrelated"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return directory


def test_user_config_is_independent_of_cwd(user_config: Path, monkeypatch, tmp_path) -> None:
    (user_config / "hks.yaml").write_text(
        "runtime:\n  ks_root: /shared/ks\n  workspace_registry: /shared/workspaces.json\n"
        "embedding:\n  model: openai:text-embedding-3-small\n"
    )
    from hks.workspace.registry import registry_path

    for cwd in [tmp_path, tmp_path / "unrelated"]:
        monkeypatch.chdir(cwd)
        assert config_value("KS_ROOT") == "/shared/ks"
        assert registry_path() == Path("/shared/workspaces.json")
        assert config_value("HKS_EMBEDDING_MODEL") == "openai:text-embedding-3-small"


def test_user_symlinks_resolve_repo_variables_from_config_target(user_config, tmp_path) -> None:
    repo = tmp_path / "repo"
    (repo / "src" / "hks").mkdir(parents=True)
    (repo / "config").mkdir()
    yaml = repo / "config" / "hks.yaml"
    yaml.write_text('runtime:\n  ks_root: "${HKS_REPO_ROOT}/data"\n')
    (user_config / "hks.yaml").symlink_to(yaml)
    env = repo / "config" / "hks.env"
    env.write_text('HKS_WORKSPACE_REGISTRY="${HKS_REPO_ROOT}/workspaces.json"\n')
    (user_config / "hks.env").symlink_to(env)
    assert config_value("KS_ROOT") == str(repo / "data")
    assert config_value("HKS_WORKSPACE_REGISTRY") == str(repo / "workspaces.json")


def test_project_config_does_not_mix_user_env(user_config, tmp_path, monkeypatch) -> None:
    (user_config / "hks.env").write_text("KS_ROOT=/unexpected\n")
    local = tmp_path / "unrelated" / "config"
    local.mkdir()
    (local / "hks.yaml").write_text("runtime:\n  ks_root: /project/ks\n")
    assert config_value("KS_ROOT") == "/project/ks"
    monkeypatch.setenv("KS_ROOT", "/explicit/ks")
    assert config_value("KS_ROOT") == "/explicit/ks"


@pytest.mark.parametrize("name", ["HKS_CONFIG_FILE", "HKS_CONFIG_ENV"])
def test_explicit_missing_config_does_not_fall_back_to_user(user_config, monkeypatch, name) -> None:
    (user_config / "hks.env").write_text("KS_ROOT=/unexpected\n")
    (user_config / "hks.yaml").write_text("runtime:\n  ks_root: /unexpected\n")
    monkeypatch.setenv(name, str(user_config / "missing.yaml"))
    assert config_value("KS_ROOT") is None
