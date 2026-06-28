"""Runtime setup for local vendored dependencies and Windows console output."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def ensure_compatible_python() -> None:
    """Relaunch scripts with Python 3.12, matching vendored binary wheels."""
    if sys.version_info[:2] == (3, 12):
        return

    if os.environ.get("DYNAMIC_ENGINE_PYTHON_RELAUNCHED") == "1":
        raise RuntimeError(
            "This project requires Python 3.12 because backend/.python_deps "
            "contains cp312 binary wheels. The process was already relaunched "
            f"but is still running Python {sys.version.split()[0]}."
        )

    bundled_python = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "python"
        / "python.exe"
    )

    if not _path_exists(bundled_python):
        raise RuntimeError(
            "This project requires Python 3.12 because backend/.python_deps "
            "contains cp312 binary wheels. Current Python is "
            f"{sys.version.split()[0]}, and the bundled Python runtime was not "
            f"found at {bundled_python}."
        )

    os.environ["DYNAMIC_ENGINE_PYTHON_RELAUNCHED"] = "1"
    if os.name == "nt":
        completed = subprocess.run([str(bundled_python), *sys.argv])
        raise SystemExit(completed.returncode)

    os.execv(str(bundled_python), [str(bundled_python), *sys.argv])


def bootstrap_runtime() -> None:
    """Make the local dependency folder behave like an installed site-package."""
    backend_dir = Path(__file__).resolve().parent
    deps_dir = backend_dir / ".python_deps"
    sqlalchemy_deps_dir = backend_dir / ".sqlalchemy_deps"

    dependency_paths = [
        sqlalchemy_deps_dir,
        deps_dir,
        deps_dir / "win32",
        deps_dir / "win32" / "lib",
        deps_dir / "pywin32_system32",
        backend_dir,
    ]

    for path in reversed(dependency_paths):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

    pywin32_dll_dir = deps_dir / "pywin32_system32"
    if _path_exists(pywin32_dll_dir) and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(pywin32_dll_dir))
        except OSError:
            pass

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    bundled_node = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
    )
    node_bin = bundled_node / "bin"
    node_modules = bundled_node / "node_modules"

    if _path_exists(node_bin):
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        node_bin_str = str(node_bin)
        if node_bin_str not in path_entries:
            os.environ["PATH"] = node_bin_str + os.pathsep + os.environ.get("PATH", "")

    if _path_exists(node_modules):
        current_node_path = os.environ.get("NODE_PATH", "")
        node_path_entries = [p for p in current_node_path.split(os.pathsep) if p]
        node_modules_str = str(node_modules)
        if node_modules_str not in node_path_entries:
            node_path_entries.insert(0, node_modules_str)
            os.environ["NODE_PATH"] = os.pathsep.join(node_path_entries)

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
