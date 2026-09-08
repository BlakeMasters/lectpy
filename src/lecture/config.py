"""Small, explicit project configuration shared by CLI execution commands."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .policy import GrantedPolicy, default_policy


class ConfigError(ValueError):
    """A project setting cannot be applied by this package version."""


def _table(value: Any, name: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a TOML table")
    unknown = set(value) - allowed
    if unknown:
        raise ConfigError(f"unsupported {name} setting(s): {', '.join(sorted(unknown))}")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    path: Path | None = None
    entry: str | None = None
    title: str | None = None
    provider: str = "trace"
    profile: str = "local-trusted"
    policy_overrides: dict[str, Any] = field(default_factory=dict)
    view: str | None = None

    def execution_policy(self, override: str | None = None) -> GrantedPolicy:
        # An explicit CLI profile selects that complete profile.
        profile = override or self.profile
        if profile == "static":
            raise ConfigError(
                "static is a delivery profile, not an execution provider; "
                "use 'lecture build' with an execution policy such as local-trusted"
            )
        try:
            policy = default_policy(profile)
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        return policy if override else replace(policy, **self.policy_overrides)


def load_project(
    source: str | None = None,
    config_path: str | None = None,
) -> ProjectConfig:
    """Discover nearest lecture.toml from the source directory (or current cwd)."""
    cwd = Path.cwd()
    if config_path:
        path = Path(config_path).resolve()
        if not path.is_file():
            raise ConfigError(f"no such config: {path}")
    else:
        start = Path(source).resolve().parent if source else cwd
        path = next(
            (p / "lecture.toml" for p in (start, *start.parents) if (p / "lecture.toml").is_file()),
            None,
        )
    if path is None:
        return ProjectConfig(root=cwd)
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    _table(data, "project", {"lecture", "runtimes", "policy", "export", "presentation"})
    lecture = _table(data.get("lecture", {}), "lecture", {"format-version", "entry", "title"})
    version = lecture.get("format-version", 1)
    if type(version) is not int or version != 1:
        raise ConfigError("lecture.format-version must be 1")
    entry = _string(lecture["entry"], "lecture.entry") if "entry" in lecture else None
    title = _string(lecture["title"], "lecture.title") if "title" in lecture else None
    runtimes = _table(data.get("runtimes", {}), "runtimes", {"python"})
    runtime = _table(runtimes.get("python", {}), "runtimes.python", {"provider"})
    provider = runtime.get("provider", "trace")
    if provider not in ("trace", "python"):
        raise ConfigError("runtimes.python.provider must be 'trace' or 'python'")
    policies = _table(data.get("policy", {}), "policy", {"default"})
    fields = {
        "network": "network",
        "process": "process",
        "filesystem-read": "fs_read",
        "filesystem-write": "fs_write",
        "allow-network-hosts": "allow_network_hosts",
        "max-output-bytes": "max_output_bytes",
        "max-events": "max_events",
        "max-wall-seconds": "max_wall_seconds",
    }
    settings = _table(policies.get("default", {}), "policy.default", {"profile", *fields})
    profile = _string(settings.get("profile", "local-trusted"), "policy.default.profile")
    overrides: dict[str, Any] = {}
    for key, value in settings.items():
        if key == "profile":
            continue
        if key in ("filesystem-read", "filesystem-write", "allow-network-hosts"):
            if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
                raise ConfigError(f"policy.default.{key} must be an array of strings")
            if key != "allow-network-hosts":
                value = [str((path.parent / v).resolve()) for v in value]
            value = tuple(value)
        elif key.startswith("max-"):
            integer = key != "max-wall-seconds"
            if (
                type(value) not in (int, float)
                or (integer and type(value) is not int)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ConfigError(
                    f"policy.default.{key} must be a positive {'integer' if integer else 'number'}"
                )
        elif key == "network" and value not in ("deny", "allowlist", "user-controlled"):
            raise ConfigError("policy.default.network must be deny, allowlist, or user-controlled")
        elif key == "process" and value not in ("deny", "sandbox", "allow"):
            raise ConfigError("policy.default.process must be deny, sandbox, or allow")
        overrides[fields[key]] = value
    exports = _table(data.get("export", {}), "export", {"static"})
    static = _table(exports.get("static", {}), "export.static", {"interactive-fallback"})
    if static.get("interactive-fallback", "recorded") != "recorded":
        raise ConfigError("export.static.interactive-fallback currently supports only 'recorded'")
    presentation = _table(data.get("presentation", {}), "presentation", {"view"})
    view = presentation.get("view")
    if view is not None and view not in ("reader", "presenter", "inspector"):
        raise ConfigError("presentation.view must be reader, presenter, or inspector")
    config = ProjectConfig(path.parent, path, entry, title, provider, profile, overrides, view)
    config.execution_policy()  # validate even for check-only usage
    return config
