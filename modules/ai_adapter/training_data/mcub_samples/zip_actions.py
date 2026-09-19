"""
StudioActions — synchronous bridge between the curses TUI thread
and the async kernel event loop.

All public methods block until the coroutine finishes (or times out).
Progress is fed to a ProgressReporter that the TUI reads on each redraw.
"""

from __future__ import annotations

import asyncio
import os
import sys
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple


class ProgressReporter:
    """
    Thread-safe log + percent accumulator.
    The TUI renders this without locking because it only reads,
    and Python's GIL makes list.append atomic enough here.
    """

    def __init__(self) -> None:
        self.percent: float      = 0.0
        self.logs:    List[str]  = []
        self._cbs:    List[Callable] = []

    def step(self, pct: float, msg: str) -> None:
        """Advance to *pct* (0.0–1.0) and append *msg* to the log."""
        self.percent = max(self.percent, min(1.0, float(pct)))
        ts    = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.logs.append(entry)
        # Notify listeners (TUI appends to global log)
        for cb in self._cbs:
            try:
                cb(self.percent, msg)
            except Exception:
                pass

    def on_update(self, cb: Callable[[float, str], None]) -> None:
        self._cbs.append(cb)


class StudioActions:
    """
    Facade that the TUI calls for every kernel operation.
    All methods run synchronously in the curses thread by dispatching
    coroutines to *loop* via run_coroutine_threadsafe().
    """

    TIMEOUT = 45  # seconds to wait for a kernel async call

    def __init__(self, kernel, loop: asyncio.AbstractEventLoop) -> None:
        self.k    = kernel
        self.loop = loop

    def _run(self, coro):
        """Block until *coro* finishes in the kernel's event loop."""
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return fut.result(timeout=self.TIMEOUT)

    def get_user_modules(self) -> List[str]:
        return sorted(self.k.loaded_modules.keys())

    def get_system_modules(self) -> List[str]:
        return sorted(self.k.system_modules.keys())

    def get_module_commands(self, name: str) -> List[str]:
        return sorted(
            cmd for cmd, owner in self.k.command_owners.items()
            if owner == name
        )

    def get_module_file(self, name: str) -> Optional[str]:
        if name in self.k.system_modules:
            p = Path(self.k.MODULES_DIR) / f"{name}.py"
        else:
            p = Path(self.k.MODULES_LOADED_DIR) / f"{name}.py"
        return str(p) if p.exists() else None

    def get_module_source(self, name: str) -> Optional[str]:
        path = self.get_module_file(name)
        if not path:
            return None
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception:
            return None

    def get_module_metadata(self, name: str) -> dict:
        source = self.get_module_source(name)
        if not source:
            return {}
        try:
            return self._run(self.k.get_module_metadata(source))
        except Exception:
            return {}

    def get_all_repo_modules(self) -> List[Tuple[str, str]]:
        """Return [(module_name, repo_url)] from all repos (slow — network)."""
        repos   = [self.k.default_repo] + list(self.k.repositories)
        results = []
        for repo in repos:
            try:
                modules = self._run(self.k.get_repo_modules_list(repo))
                for m in modules:
                    results.append((m, repo))
            except Exception:
                pass
        return results

    def search_repos(self, query: str) -> List[Tuple[str, str]]:
        """Filter all repo modules by *query* (case-insensitive substring)."""
        q = query.lower()
        return [(m, r) for m, r in self.get_all_repo_modules()
                if q in m.lower()]

    def load_module(
        self,
        file_path: str,
        module_name: str,
        reporter: ProgressReporter,
    ) -> Tuple[bool, str]:
        """
        Full install pipeline:
          read → metadata → copy to modules_loaded → unload old → kernel load
        """
        try:
            reporter.step(0.03, f"=- Starting load: '{module_name}'")
            reporter.step(0.06, f"   File: {file_path}")

            if not os.path.exists(file_path):
                reporter.step(1.0, "=X File not found")
                return False, "File not found"

            reporter.step(0.12, "=- Reading source file...")
            source = Path(file_path).read_text(encoding="utf-8")
            reporter.step(0.18, f"=> Source read ({len(source)} bytes)")

            # Metadata
            reporter.step(0.22, "=- Parsing module metadata...")
            try:
                meta = self._run(self.k.get_module_metadata(source))
                reporter.step(0.28, f"   Author:      {meta.get('author', 'unknown')}")
                reporter.step(0.30, f"   Version:     {meta.get('version', '?')}")
                desc = (meta.get("description") or "")[:80]
                if desc:
                    reporter.step(0.32, f"   Description: {desc}")
            except Exception as e:
                reporter.step(0.28, f"=! Metadata parse warning: {e}")

            # Compatibility check (simple heuristic)
            reporter.step(0.35, "=- Checking compatibility...")
            if "from hikka" in source or "from heroku" in source.lower():
                reporter.step(1.0, "=X Incompatible module (Hikka/Heroku type)")
                return False, "Incompatible module type"
            reporter.step(0.40, "=> Module compatible")

            # Copy to modules_loaded/
            target_dir  = Path(self.k.MODULES_LOADED_DIR)
            target_path = target_dir / f"{module_name}.py"
            if Path(file_path).resolve() != target_path.resolve():
                reporter.step(0.45, f"=- Copying to {target_path}...")
                shutil.copy2(file_path, target_path)
                reporter.step(0.50, "=> File saved to modules_loaded/")
                file_path = str(target_path)
            else:
                reporter.step(0.50, "=> File already in modules_loaded/")

            # Unload stale version
            if module_name in self.k.loaded_modules:
                reporter.step(0.55, f"=- Unloading old version of '{module_name}'...")
                self.k.unregister_module_commands(module_name)
                del self.k.loaded_modules[module_name]
                sys.modules.pop(module_name, None)
                reporter.step(0.60, "=> Old version unloaded")

            # Kernel load
            reporter.step(0.65, "=- Loading module into kernel...")
            ok, msg = self._run(
                self.k.load_module_from_file(file_path, module_name, False)
            )

            if ok:
                cmds = self.get_module_commands(module_name)
                reporter.step(0.90, f"=> Commands registered: {len(cmds)}")
                if cmds:
                    prefix = self.k.custom_prefix
                    reporter.step(0.95,
                                  "   " + "  ".join(f"{prefix}{c}" for c in cmds[:6]))
                reporter.step(1.0, f"OK Module '{module_name}' loaded successfully")
                return True, f"'{module_name}' loaded"
            else:
                reporter.step(1.0, f"=X Kernel load failed: {msg}")
                return False, msg

        except Exception as e:
            reporter.step(1.0, f"=X Critical: {e}")
            reporter.step(1.0, traceback.format_exc().split("\n")[-2])
            return False, str(e)

    def unload_module(
        self,
        name: str,
        reporter: ProgressReporter,
    ) -> Tuple[bool, str]:
        """Unload module from kernel, keep file on disk."""
        try:
            reporter.step(0.10, f"=- Unloading '{name}'...")

            is_loaded  = name in self.k.loaded_modules
            is_system  = name in self.k.system_modules

            if not is_loaded and not is_system:
                reporter.step(1.0, f"=X '{name}' is not loaded")
                return False, "Module not loaded"

            reporter.step(0.35, "=- Unregistering commands...")
            self.k.unregister_module_commands(name)

            reporter.step(0.60, "=- Removing from registry...")
            if is_loaded:
                del self.k.loaded_modules[name]
            else:
                del self.k.system_modules[name]
            sys.modules.pop(name, None)

            reporter.step(1.0, f"OK '{name}' unloaded successfully")
            return True, f"'{name}' unloaded"
        except Exception as e:
            reporter.step(1.0, f"=X Error: {e}")
            return False, str(e)

    def delete_module(
        self,
        name: str,
        reporter: ProgressReporter,
    ) -> Tuple[bool, str]:
        """Unload module AND delete its .py file from disk."""
        ok, msg = self.unload_module(name, reporter)
        path = self.get_module_file(name)
        if path and os.path.exists(path):
            reporter.step(0.92, f"=- Deleting {path}...")
            try:
                os.remove(path)
                reporter.step(1.0, "OK File deleted from disk")
            except Exception as e:
                reporter.step(1.0, f"=! Could not delete file: {e}")
        return ok, msg

    def reload_module(
        self,
        name: str,
        reporter: ProgressReporter,
    ) -> Tuple[bool, str]:
        """Reload module from its current file on disk."""
        reporter.step(0.05, f"=- Reloading '{name}'...")

        path      = self.get_module_file(name)
        is_system = name in self.k.system_modules

        if not path:
            reporter.step(1.0, f"=X Cannot find file for '{name}'")
            return False, "File not found"

        reporter.step(0.20, "=- Unregistering old commands...")
        self.k.unregister_module_commands(name)

        registry = self.k.system_modules if is_system else self.k.loaded_modules
        registry.pop(name, None)
        sys.modules.pop(name, None)
        reporter.step(0.35, "=> Module cleared from registry")

        reporter.step(0.40, "=- Re-loading from file...")
        try:
            ok, msg = self._run(
                self.k.load_module_from_file(path, name, is_system)
            )
            if ok:
                cmds = self.get_module_commands(name)
                reporter.step(0.95, f"=> {len(cmds)} command(s) restored")
                reporter.step(1.0, f"OK '{name}' reloaded successfully")
                return True, f"'{name}' reloaded"
            else:
                reporter.step(1.0, f"=X Reload failed: {msg}")
                return False, msg
        except Exception as e:
            reporter.step(1.0, f"=X Error: {e}")
            return False, str(e)

    def create_module(
        self,
        name: str,
        code: str,
        reporter: ProgressReporter,
    ) -> Tuple[bool, str]:
        """Write *code* to modules_loaded/<name>.py and load it."""
        target = Path(self.k.MODULES_LOADED_DIR) / f"{name}.py"
        reporter.step(0.05, f"=- Creating module '{name}'...")
        reporter.step(0.10, f"   Target: {target}")

        try:
            target.write_text(code, encoding="utf-8")
            reporter.step(0.20, f"=> File written ({len(code)} bytes)")
        except Exception as e:
            reporter.step(1.0, f"=X Write error: {e}")
            return False, str(e)

        return self.load_module(str(target), name, reporter)

    def save_module_source(
        self,
        name: str,
        code: str,
        reporter: ProgressReporter,
    ) -> Tuple[bool, str]:
        """Save edited code and reload the module."""
        return self.create_module(name, code, reporter)

    def download_and_install(
        self,
        repo_url: str,
        module_name: str,
        reporter: ProgressReporter,
    ) -> Tuple[bool, str]:
        """Download module source from *repo_url* and load it."""
        reporter.step(0.05, f"=- Downloading '{module_name}' from repo...")
        reporter.step(0.08, f"   {repo_url}/{module_name}.py")

        try:
            source = self._run(
                self.k.download_module_from_repo(repo_url, module_name)
            )
            if not source:
                reporter.step(1.0, "=X Download returned empty — module not found")
                return False, "Module not found in repository"

            reporter.step(0.30, f"=> Downloaded {len(source)} bytes")

            target = Path(self.k.MODULES_LOADED_DIR) / f"{module_name}.py"
            target.write_text(source, encoding="utf-8")
            reporter.step(0.40, f"=> Saved to {target}")

            return self.load_module(str(target), module_name, reporter)

        except Exception as e:
            reporter.step(1.0, f"=X Error: {e}")
            return False, str(e)

    def update_from_repo(
        self,
        name: str,
        reporter: ProgressReporter,
    ) -> Tuple[bool, str]:
        """Find *name* in any repo and re-install it."""
        reporter.step(0.02, f"=- Looking for '{name}' in repositories...")
        repos = [self.k.default_repo] + list(self.k.repositories)

        for idx, repo in enumerate(repos):
            pct = 0.05 + 0.25 * (idx / max(len(repos), 1))
            reporter.step(pct, f"=- Checking repo {idx + 1}/{len(repos)}: {repo}")
            try:
                modules = self._run(self.k.get_repo_modules_list(repo))
                if name in modules:
                    reporter.step(0.35, f"=> Found '{name}' in repo!")
                    return self.download_and_install(repo, name, reporter)
                reporter.step(pct + 0.01, f"   Not in this repo")
            except Exception as e:
                reporter.step(pct, f"=! Repo error: {e}")

        reporter.step(1.0, f"=X '{name}' not found in any repository")
        return False, "Not found in any repository"
