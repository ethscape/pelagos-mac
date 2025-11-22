"""Hook implementations for Pelagos common action filters."""

from importlib import import_module
from pathlib import Path
from typing import Dict, Callable, Any

HookFunction = Callable[[Path, Dict[str, Any]], bool]


class HookRegistry:
    def __init__(self):
        self._hooks: Dict[str, HookFunction] = {}

    def register(self, name: str, func: HookFunction) -> None:
        self._hooks[name] = func

    def get(self, name: str) -> HookFunction:
        return self._hooks[name]

    def resolve(self, name: str) -> HookFunction:
        if name in self._hooks:
            return self._hooks[name]
        module = import_module(f"hooks.{name}")
        if hasattr(module, "register"):
            module.register(self)
        if name not in self._hooks:
            raise KeyError(f"Hook '{name}' did not register correctly")
        return self._hooks[name]


registry = HookRegistry()
