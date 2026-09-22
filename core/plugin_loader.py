"""Auto-discovery of plugins under ``plugins/``.

Scans the package for modules (skipping dunder/private names), imports each,
and collects plugin instances. A module contributes a plugin if it either:

* defines ``PLUGIN`` (an instance or a Plugin subclass), or
* defines any subclass of ``Plugin`` at module level.

Import errors in one plugin never break the others — they're collected and
reported so the UI can show which plugin failed and why.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field

from core.plugin_base import Plugin


@dataclass
class LoadResult:
    plugins: list[Plugin] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (module, error)


def _instantiate(obj) -> Plugin | None:
    """Turn a class or instance into a Plugin instance, or None."""
    if isinstance(obj, Plugin):
        return obj
    if inspect.isclass(obj) and issubclass(obj, Plugin) and obj is not Plugin:
        try:
            return obj()  # type: ignore[call-arg]
        except Exception:
            return None
    return None


def load_plugins(package: str = "plugins") -> LoadResult:
    """Discover and instantiate all plugins in ``package``."""
    result = LoadResult()
    pkg = importlib.import_module(package)

    for mod_info in pkgutil.iter_modules(pkg.__path__):
        name = mod_info.name
        if name.startswith("__"):
            continue
        full = f"{package}.{name}"
        try:
            module = importlib.import_module(full)
        except Exception as exc:  # keep other plugins alive
            result.errors.append((full, f"{type(exc).__name__}: {exc}"))
            continue

        found: list[Plugin] = []
        # Prefer an explicit PLUGIN export.
        if hasattr(module, "PLUGIN"):
            inst = _instantiate(getattr(module, "PLUGIN"))
            if inst is not None:
                found.append(inst)

        # Otherwise (or additionally) collect Plugin subclasses defined here.
        if not found:
            for _, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and obj.__module__ == full:
                    inst = _instantiate(obj)
                    if inst is not None:
                        found.append(inst)

        result.plugins.extend(found)

    # Stable ordering: by category then name for a tidy menu.
    result.plugins.sort(key=lambda p: (p.category.lower(), p.name.lower()))
    return result
