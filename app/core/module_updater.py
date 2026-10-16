"""Atomic and safe background module downloader with SHA-256 verification and hot-reloading triggers.
All updates, new files, and temporary files are strictly sandboxed inside the dedicated `modules/` folder.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

import httpx

from .dynamic_loader import DynamicModuleManager, dynamic_manager, validate_module_name

logger = logging.getLogger(__name__)


def compute_sha256(file_path: Path) -> str:
    """Computes the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


class ModuleUpdater:
    """
    Background worker that polls a remote manifest.json,
    downloads updated dynamic modules, verifies their cryptographic integrity,
    performs atomic replacements, and triggers hot-reloads.
    Strictly sandboxed inside the dedicated modules/ directory.
    """

    def __init__(
        self,
        manifest_url: str,
        loader: DynamicModuleManager | None = None,
        poll_interval_seconds: int = 3600,
        on_module_updated: Callable[[str, str], None] | None = None,
    ):
        self.manifest_url = manifest_url.strip()
        self.loader = loader or dynamic_manager
        self.poll_interval = poll_interval_seconds
        self.on_module_updated = on_module_updated
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def check_and_update(self, http_client: httpx.Client | None = None) -> list[str]:
        """
        Synchronously checks the remote manifest, downloads any modified/updated modules,
        verifies SHA-256 integrity, replaces them atomically, and hot-reloads them.
        Returns a list of successfully updated module names.
        """
        if not self.manifest_url:
            logger.debug("No manifest URL provided for ModuleUpdater.")
            return []

        client = http_client or httpx.Client(timeout=30)
        close_client = http_client is None
        updated_modules: list[str] = []

        try:
            logger.info("Checking remote manifest: %s", self.manifest_url)
            resp = client.get(self.manifest_url)
            resp.raise_for_status()
            manifest = resp.json()

            modules = manifest.get("modules", [])
            if not isinstance(modules, list):
                logger.warning("Invalid manifest structure: 'modules' must be a list")
                return []

            for item in modules:
                raw_name = item.get("name")
                download_url = item.get("url")
                expected_sha = (item.get("sha256") or "").strip().lower()
                version = item.get("version", "unknown")

                if not raw_name or not download_url or not expected_sha:
                    logger.warning("Skipping incomplete module entry in manifest: %s", item)
                    continue

                try:
                    clean_name = validate_module_name(raw_name)
                except ValueError as val_err:
                    logger.warning("Skipping rejected module name '%s': %s", raw_name, val_err)
                    continue

                if self._process_module_update(client, clean_name, download_url, expected_sha, version):
                    updated_modules.append(clean_name)

        except Exception as e:
            logger.error("Failed to check or apply dynamic module updates: %s", e)
        finally:
            if close_client:
                client.close()

        return updated_modules

    def _process_module_update(
        self, client: httpx.Client, name: str, download_url: str, expected_sha: str, version: str
    ) -> bool:
        """Downloads, verifies, atomically replaces, and hot-reloads a single module strictly in modules/."""
        clean_name = validate_module_name(name)
        modules_dir = self.loader.modules_dir.resolve()
        target_file = (modules_dir / f"{clean_name}.py").resolve()
        temp_file = (modules_dir / f"{clean_name}.py.tmp_{os.getpid()}_{int(time.time())}").resolve()

        # Strict sandbox assertion: Both target and temporary files MUST reside in modules_dir
        if target_file.parent != modules_dir or temp_file.parent != modules_dir:
            logger.error("Security violation: Attempted to write dynamic module '%s' outside modules/ folder!", clean_name)
            return False

        # If current target file already matches expected sha, skip redownload
        if target_file.exists():
            current_sha = compute_sha256(target_file)
            if current_sha == expected_sha:
                logger.debug("Module '%s' in %s is already at target version (%s), skipping.", clean_name, modules_dir, version)
                return False

        logger.info("New version detected for '%s' (v%s). Downloading to %s", clean_name, version, target_file)

        try:
            # 1. Download to temporary file strictly within modules/
            with client.stream("GET", download_url) as stream:
                stream.raise_for_status()
                with temp_file.open("wb") as f:
                    for chunk in stream.iter_bytes():
                        f.write(chunk)

            # 2. Verify SHA-256 integrity
            downloaded_sha = compute_sha256(temp_file)
            if downloaded_sha != expected_sha:
                raise ValueError(
                    f"Integrity check failed for {clean_name}! Expected {expected_sha}, got {downloaded_sha}"
                )

            # 3. Quick syntax check on the downloaded file before replacing
            source = temp_file.read_text(encoding="utf-8")
            compile(source, str(temp_file), "exec")

            # 4. Atomic file replacement within modules/
            temp_file.replace(target_file)
            logger.info("Atomically replaced '%s.py' in modules/ with verified new version (%s)", clean_name, version)

            # 5. Hot-reload module in memory
            reloaded = self.loader.reload_module(clean_name)
            if reloaded:
                if self.on_module_updated:
                    try:
                        self.on_module_updated(clean_name, version)
                    except Exception as cb_err:
                        logger.error("Error in on_module_updated callback: %s", cb_err)
                return True
            else:
                logger.warning("Module '%s' was updated on disk in modules/ but in-memory reload had to rollback.", clean_name)
                return False

        except Exception as e:
            logger.error("Failed to update module '%s' in modules/: %s", clean_name, e)
            # 6. Cleanup temporary file on failure
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            return False

    def start_background_updater(self) -> None:
        """Starts periodic background polling thread."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="ModuleUpdaterThread", daemon=True)
            self._thread.start()
            logger.info("Background ModuleUpdater thread started for %s (poll interval: %ds).",
                        self.loader.modules_dir, self.poll_interval)

    def stop_background_updater(self) -> None:
        """Stops the background updater thread cleanly."""
        with self._lock:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3)
            self._thread = None
            logger.info("Background ModuleUpdater thread stopped.")

    def _run_loop(self) -> None:
        # Initial check after 5 seconds of launch
        if self._stop_event.wait(timeout=5):
            return
        self.check_and_update()

        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self.poll_interval):
                break
            self.check_and_update()
