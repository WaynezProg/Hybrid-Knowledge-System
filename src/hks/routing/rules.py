"""Load and validate Phase 2 routing configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

from hks.core.config import config_value
from hks.core.paths import resolve_ks_root
from hks.core.schema import Route
from hks.errors import ExitCode, KSError


@dataclass(frozen=True, slots=True)
class RoutingRule:
    id: str
    priority: int
    target_route: Route
    keywords_zh: tuple[str, ...]
    keywords_en: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoutingRuleSet:
    version: int
    default_route: Route
    rules: tuple[RoutingRule, ...]


def default_rules_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "routing_rules.yaml"


def resolve_rules_path(ks_root: Path | str | None = None) -> Path:
    env_path = config_value("HKS_ROUTING_RULES")
    if env_path:
        return Path(env_path).expanduser().resolve(strict=False)

    runtime_path = resolve_ks_root(ks_root) / "config" / "routing_rules.yaml"
    if runtime_path.exists():
        return runtime_path

    return default_rules_path()


def _yaml_loader() -> YAML:
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    return yaml


def load_rules(ks_root: Path | str | None = None) -> RoutingRuleSet:
    path = resolve_rules_path(ks_root)
    if not path.exists():
        raise KSError(
            "找不到 routing rules",
            exit_code=ExitCode.GENERAL,
            code="ROUTING_RULES_MISSING",
            details=[str(path)],
        )

    try:
        payload = cast(dict[str, Any], _yaml_loader().load(path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise KSError(
            "routing rules YAML 無法解析",
            exit_code=ExitCode.GENERAL,
            code="ROUTING_RULES_INVALID",
            details=[str(exc)],
        ) from exc

    default_route = cast(Route, payload["default_route"])
    if default_route not in {"wiki", "graph", "vector"}:
        raise KSError(
            "routing rules 預設路由非法",
            exit_code=ExitCode.GENERAL,
            code="ROUTING_RULES_INVALID",
            details=[f"default_route={default_route}"],
        )

    seen_priorities: set[int] = set()
    rules: list[RoutingRule] = []
    for raw_rule in cast(list[dict[str, Any]], payload.get("rules", [])):
        target_route = cast(Route, raw_rule["target_route"])
        if target_route not in {"wiki", "graph", "vector"}:
            raise KSError(
                "routing rules route 非法",
                exit_code=ExitCode.GENERAL,
                code="ROUTING_RULES_INVALID",
                details=[f"rule={raw_rule.get('id')} target_route={target_route}"],
            )

        priority = int(raw_rule["priority"])
        if priority in seen_priorities:
            raise KSError(
                "routing rules priority 重複",
                exit_code=ExitCode.GENERAL,
                code="ROUTING_RULES_INVALID",
                details=[f"priority={priority}"],
            )
        seen_priorities.add(priority)

        keywords = cast(dict[str, list[str]], raw_rule.get("keywords", {}))
        zh = tuple(keywords.get("zh", []))
        en = tuple(keyword.lower() for keyword in keywords.get("en", []))
        if not zh and not en:
            raise KSError(
                "routing rule 缺少 keywords",
                exit_code=ExitCode.GENERAL,
                code="ROUTING_RULES_INVALID",
                details=[f"rule={raw_rule.get('id')}"],
            )
        rules.append(
            RoutingRule(
                id=str(raw_rule["id"]),
                priority=priority,
                target_route=target_route,
                keywords_zh=zh,
                keywords_en=en,
            )
        )

    rules.sort(key=lambda rule: rule.priority)
    return RoutingRuleSet(
        version=int(payload.get("version", 1)),
        default_route=default_route,
        rules=tuple(rules),
    )
