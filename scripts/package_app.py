"""Utility helpers to build standalone packages using PyInstaller."""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
ENTRY_SCRIPT = PROJECT_ROOT / "main.py"


def build_for_platform(target: str, extra_args: List[str] | None = None) -> None:
    """Build the project for the given platform using PyInstaller."""
    command = [
        "pyinstaller",
        "--name", f"SamsungUnlockPro-{target}",
        "--clean",
        "--onefile",
        "--add-data",
        f"requirements.txt{os.pathsep}.",
        str(ENTRY_SCRIPT),
    ]

    if extra_args:
        command.extend(extra_args)

    print(f"[packager] Building for {target}: {' '.join(command)}")
    subprocess.run(command, check=True)


def normalize_platform_name() -> str:
    system = platform.system().lower()
    if system.startswith("darwin"):
        return "macos"
    if system.startswith("windows"):
        return "windows"
    return "linux"


def clean_dist() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)


def build_all(targets: List[str]) -> None:
    clean_dist()
    original_cwd = os.getcwd()
    os.chdir(PROJECT_ROOT)
    try:
        for target in targets:
            build_for_platform(target)
    finally:
        os.chdir(original_cwd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package Samsung Unlock Pro for distribution")
    parser.add_argument(
        "--targets",
        nargs="*",
        default=[normalize_platform_name()],
        help="Target platforms: linux, windows, macos (default: current platform)",
    )
    parser.add_argument(
        "--extra-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Additional arguments passed directly to PyInstaller",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.extra_args:
        for target in args.targets:
            build_for_platform(target, args.extra_args)
    else:
        build_all(args.targets)


if __name__ == "__main__":
    main()
