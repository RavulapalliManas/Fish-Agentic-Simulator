"""Build the Python backend into a standalone executable with PyInstaller."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    backend_dir = Path(__file__).resolve().parent
    dist_dir = backend_dir / "dist"
    build_dir = backend_dir / "build"
    cache_dir = backend_dir / ".pyinstaller-cache"

    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)

    cache_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        "fish-backend",
        "--paths",
        str(backend_dir / "app"),
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        "--exclude-module",
        "PyQt5",
        "--exclude-module",
        "PyQt5.QtCore",
        "--exclude-module",
        "PyQt5.QtGui",
        "--exclude-module",
        "PyQt5.QtWidgets",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "IPython",
        "--exclude-module",
        "tkinter",
        str(backend_dir / "main.py"),
    ]
    env = dict(os.environ)
    env["PYINSTALLER_CONFIG_DIR"] = str(cache_dir)
    subprocess.run(command, check=True, env=env)


if __name__ == "__main__":
    main()
