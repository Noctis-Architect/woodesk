"""Dynamic Module Loader with hot-reloading, cache management, and self-healing fallback.
All dynamic modules are strictly isolated within the dedicated `modules/` directory.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import re
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

logger = logging.getLogger(__name__)


def get_default_modules_dir() -> Path:
    """Returns the dedicated modules directory (strictly `modules/` at project root)."""
    override = os.environ.get("WOODESK_MODULES_DIR")
    if override:
        p = Path(override).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Dedicated 'modules/' directory at root of project
    root_modules = Path(__file__).resolve().parent.parent.parent / "modules"
    root_modules.mkdir(parents=True, exist_ok=True)
    return root_modules.resolve()


def validate_module_name(name: str) -> str:
    """Ensures module name is clean and strictly alphanumeric to prevent directory traversal."""
    cleaned = (name or "").strip()
    if not cleaned or not re.match(r"^[a-zA-Z0-9_-]+$", cleaned):
        raise ValueError(f"Invalid dynamic module name '{name}'. Only letters, numbers, underscores, and hyphens are permitted.")
    return cleaned


class DynamicLoaderError(Exception):
    """Base exception for dynamic loader failures."""
    pass


class DynamicModuleManager:
    """Manages discovery, dynamic loading, hot-reloading, and safe execution of dynamic modules strictly in modules/."""

    def __init__(self, modules_dir: Path | str | None = None):
        self._lock = threading.RLock()
        self._modules: dict[str, ModuleType] = {}
        self._last_known_good: dict[str, ModuleType] = {}
        self.modules_dir = Path(modules_dir).resolve() if modules_dir else get_default_modules_dir()
        self.modules_dir.mkdir(parents=True, exist_ok=True)

        # Ensure dedicated modules directory is in sys.path
        dir_str = str(self.modules_dir)
        if dir_str not in sys.path:
            sys.path.insert(0, dir_str)

    def _resolve_module_file(self, name: str) -> Path:
        """Resolves module path and guarantees it resides strictly inside self.modules_dir."""
        clean_name = validate_module_name(name)
        target = (self.modules_dir / f"{clean_name}.py").resolve()
        if target.parent != self.modules_dir:
            raise PermissionError(f"Access denied: Dynamic module '{clean_name}' must reside strictly in {self.modules_dir}")
        return target

    def discover_modules(self) -> list[str]:
        """Discovers all available module names (.py) strictly within the modules directory."""
        with self._lock:
            modules = []
            for file in self.modules_dir.glob("*.py"):
                if not file.name.startswith(("_", ".")):
                    modules.append(file.stem)
            return sorted(modules)

    def load_module(self, name: str) -> ModuleType:
        """Loads a module by name from the dedicated modules directory."""
        clean_name = validate_module_name(name)
        with self._lock:
            if clean_name in self._modules:
                return self._modules[clean_name]

            module_file = self._resolve_module_file(clean_name)
            if not module_file.exists():
                raise FileNotFoundError(f"Dynamic module file not found in modules folder: {module_file}")

            try:
                module_qname = f"modules.{clean_name}"
                spec = importlib.util.spec_from_file_location(module_qname, str(module_file))
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot create module spec for {clean_name}")

                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

                self._modules[clean_name] = module
                self._last_known_good[clean_name] = module
                logger.info("Loaded dynamic module '%s' from %s (version: %s)",
                            clean_name, module_file, getattr(module, "__version__", "unknown"))
                return module
            except Exception as e:
                logger.error("Failed to load module '%s': %s", clean_name, e, exc_info=True)
                raise DynamicLoaderError(f"Error loading module {clean_name}: {e}") from e

    def reload_module(self, name: str) -> bool:
        """
        Hot-reloads a module from the dedicated modules directory.
        If the newly updated file contains syntax or import errors,
        it automatically falls back to the previous stable in-memory instance.
        """
        clean_name = validate_module_name(name)
        with self._lock:
            current_instance = self._modules.get(clean_name) or self._last_known_good.get(clean_name)
            module_file = self._resolve_module_file(clean_name)

            if not module_file.exists():
                logger.error("Cannot reload module '%s': file %s does not exist", clean_name, module_file)
                return False

            try:
                # Compile check first to catch SyntaxError before altering in-memory state
                source_code = module_file.read_text(encoding="utf-8")
                compiled_code = compile(source_code, str(module_file), "exec")

                module_qname = f"modules.{clean_name}"
                spec = importlib.util.spec_from_file_location(module_qname, str(module_file))
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot resolve spec for {clean_name}")

                new_module = importlib.util.module_from_spec(spec)
                exec(compiled_code, new_module.__dict__)

                sys.modules[module_qname] = new_module
                self._modules[clean_name] = new_module
                self._last_known_good[clean_name] = new_module

                logger.info("Hot-reloaded dynamic module '%s' successfully (new version: %s)",
                            clean_name, getattr(new_module, "__version__", "unknown"))
                return True

            except (SyntaxError, ImportError) as e:
                logger.error("Critical error while hot-reloading '%s' (Syntax/Import error): %s. Rolling back.", clean_name, e)
                self._fallback(clean_name, current_instance)
                return False
            except Exception as e:
                logger.error("Unexpected runtime error while hot-reloading '%s': %s. Rolling back.", clean_name, e, exc_info=True)
                self._fallback(clean_name, current_instance)
                return False

    def _fallback(self, name: str, fallback_instance: ModuleType | None) -> None:
        """Restores previous stable in-memory instance."""
        if fallback_instance is not None:
            self._modules[name] = fallback_instance
            sys.modules[f"modules.{name}"] = fallback_instance
            logger.warning("Restored previous stable in-memory instance for '%s'", name)
        else:
            logger.error("No previous stable instance available for '%s'", name)

    def reload_all(self) -> dict[str, bool]:
        """Reloads all loaded modules. Returns mapping of module name to success status."""
        with self._lock:
            results = {}
            for name in list(self._modules.keys()):
                results[name] = self.reload_module(name)
            return results

    def get_service(self, name: str) -> ModuleType | None:
        """Retrieves module instance safely. Loads it from modules/ if not already loaded."""
        clean_name = validate_module_name(name)
        with self._lock:
            if clean_name in self._modules:
                return self._modules[clean_name]
            try:
                return self.load_module(clean_name)
            except Exception:
                return self._last_known_good.get(clean_name)

    def execute(self, module_name: str, func_name: str, *args, **kwargs) -> Any:
        """
        Safely executes a dynamic function by name with automatic fault-tolerance.
        If current execution fails due to a corrupted module state, attempts fallback.
        """
        clean_name = validate_module_name(module_name)
        service = self.get_service(clean_name)
        if not service:
            raise DynamicLoaderError(f"Dynamic module '{clean_name}' is not available in modules directory")

        fn: Callable | None = getattr(service, func_name, None)
        if not callable(fn):
            raise AttributeError(f"Module '{clean_name}' does not export callable function '{func_name}'")

        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.error("Error executing %s.%s: %s", clean_name, func_name, e)
            fallback = self._last_known_good.get(clean_name)
            if fallback and fallback is not service:
                fb_fn = getattr(fallback, func_name, None)
                if callable(fb_fn):
                    logger.warning("Retrying %s.%s with previous stable module instance", clean_name, func_name)
                    return fb_fn(*args, **kwargs)
            raise


# Global singleton manager operating strictly on the dedicated modules/ directory
dynamic_manager = DynamicModuleManager()
