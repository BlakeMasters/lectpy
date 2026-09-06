"""Plugin / provider registries — the microkernel's extension surface.

Core knows media types, command ids, provider ids — never Torch, Vega, Deno,
or CUDA specifics. Those live in plugins registered here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RendererContribution:
    mime_types: tuple[str, ...]
    component: str  # component id / module path
    trusted: bool = False  # trusted host UI vs sandboxed lecture component


@dataclass
class CommandContribution:
    id: str
    title: str
    keybinding: str = ""


@dataclass
class ExecutionProviderContribution:
    id: str
    display_name: str
    factory: Any = None


class RendererRegistry:
    def __init__(self) -> None:
        self._by_mime: dict[str, RendererContribution] = {}

    def register(self, contrib: RendererContribution) -> None:
        for mime in contrib.mime_types:
            if mime in self._by_mime:
                raise ValueError(f"renderer already registered for {mime}")
            self._by_mime[mime] = contrib

    def resolve(self, mime: str) -> RendererContribution | None:
        return self._by_mime.get(mime)

    def mimes(self) -> list[str]:
        return sorted(self._by_mime)


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, CommandContribution] = {}

    def register(self, contrib: CommandContribution) -> None:
        if contrib.id in self._commands:
            raise ValueError(f"command already registered: {contrib.id}")
        self._commands[contrib.id] = contrib

    def all(self) -> list[CommandContribution]:
        return sorted(self._commands.values(), key=lambda c: c.id)


class ExecutionRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ExecutionProviderContribution] = {}

    def register(self, contrib: ExecutionProviderContribution) -> None:
        if contrib.id in self._providers:
            raise ValueError(f"execution provider already registered: {contrib.id}")
        self._providers[contrib.id] = contrib

    def get(self, id: str) -> ExecutionProviderContribution | None:
        return self._providers.get(id)

    def ids(self) -> list[str]:
        return sorted(self._providers)
