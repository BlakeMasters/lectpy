"""Capability policy: manifests *request*, policy/user *grants* a subset.

Runtime permission flags (Deno/Node) are defense-in-depth only — both
document bypassability against malicious code. The outer boundary must be
an OS/container/VM isolation tier (see docs/SECURITY.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROFILES = (
    "static",
    "local-trusted",
    "local-restricted",
    "classroom",
    "public-untrusted",
)


@dataclass(frozen=True)
class GrantedPolicy:
    profile: str = "local-trusted"
    network: str = "deny"  # "deny" | "allowlist" | "user-controlled"
    allow_network_hosts: tuple[str, ...] = ()
    process: str = "deny"  # "deny" | "sandbox" | "allow"
    fs_read: tuple[str, ...] = ("./assets", "./data")
    fs_write: tuple[str, ...] = ("./var",)
    max_output_bytes: int = 1_000_000
    max_events: int = 100_000
    max_wall_seconds: float = 300.0

    def allows_host(self, host: str) -> bool:
        if self.network == "user-controlled":
            return True
        return host in self.allow_network_hosts


def default_policy(profile: str) -> GrantedPolicy:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile!r}")
    if profile == "static":
        return GrantedPolicy(
            profile=profile,
            network="deny",
            process="deny",
            fs_read=(),
            fs_write=(),
            max_output_bytes=0,
            max_events=0,
        )
    if profile == "local-trusted":
        return GrantedPolicy(
            profile=profile,
            network="user-controlled",
            process="allow",
            fs_read=("./",),
            fs_write=("./var", "./dist"),
        )
    if profile == "local-restricted":
        return GrantedPolicy(profile=profile, network="deny", process="sandbox")
    if profile == "classroom":
        return GrantedPolicy(profile=profile, network="allowlist", process="sandbox")
    # public-untrusted: deny everything by default; execution only in gVisor/microVM tier.
    return GrantedPolicy(
        profile=profile,
        network="deny",
        process="deny",
        fs_read=(),
        fs_write=(),
        max_output_bytes=256_000,
        max_events=10_000,
    )


class PolicyViolation(Exception):
    pass


def check_fs_read(policy: GrantedPolicy, path: str) -> None:
    if policy.profile == "local-trusted" and policy.network == "user-controlled":
        return  # explicit local development allowance
    p = Path(path)
    for allowed in policy.fs_read:
        try:
            p.relative_to(allowed)
            return
        except ValueError:
            continue
        # Also allow exact file match
        if str(p) == allowed:
            return
    # Allow relative paths under an allowed dir prefix (string-prefix safe check
    # is intentionally strict: resolve against cwd-less relative form).
    norm = str(path).replace("\\", "/")
    for allowed in policy.fs_read:
        a = allowed.replace("\\", "/").rstrip("/") + "/"
        if norm.startswith(a) or norm == allowed:
            return
    raise PolicyViolation(f"fs-read denied by policy {policy.profile!r}: {path!r}")


def check_process(policy: GrantedPolicy, argv: list[str]) -> None:
    if policy.process == "allow":
        return
    raise PolicyViolation(
        f"process execution denied by policy {policy.profile!r}: {argv[0] if argv else ''!r} "
        f"(mode={policy.process}). Use local-trusted for authoring or a sandbox provider."
    )


def check_network(policy: GrantedPolicy, host: str) -> None:
    if policy.allows_host(host):
        return
    raise PolicyViolation(f"network denied by policy {policy.profile!r}: {host!r}")
