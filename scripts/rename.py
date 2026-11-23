"""Rename the skeleton so the copy is yours: package, distribution name, container command, tests.

Usage (from the repository root):

    uv run python scripts/rename.py --package acmeserver --name "Acme Server"
    uv lock                       # the lock file carries the project name
    uv sync && uv run pytest -q   # proves the rename did not break an import

Doing this by hand misses one of the places the name lives: `Dockerfile`'s CMD and the three test
imports are the two that break everything while still looking fine.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OLD_PACKAGE = "mcpserver"
OLD_NAME = "McpSquelette"
TEXT_SUFFIXES = {".py", ".toml", ".yaml", ".yml", ".md", ".example", ".cfg", ".txt"}
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rename this McpSquelette copy.")
    parser.add_argument("--package", required=True, help="New import package, e.g. `acmeserver`.")
    parser.add_argument("--name", default=None, help="Display name sent to clients, e.g. `Acme Server`.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would change without touching a file.",
    )
    return parser.parse_args(argv)


def validate(package: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", package):
        sys.exit(f"error: `{package}` must be a valid Python package name (lowercase, underscores).")
    if (REPO_ROOT / "src" / package).exists():
        sys.exit(f"error: src/{package} already exists.")


def tracked_text_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in {".gitignore", ".env.example", "Dockerfile"}:
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    validate(args.package)

    old_dir = REPO_ROOT / "src" / OLD_PACKAGE
    new_dir = REPO_ROOT / "src" / args.package
    changed: list[Path] = []

    for path in tracked_text_files():
        text = path.read_text()
        updated = text.replace(OLD_PACKAGE, args.package)
        if args.name:
            updated = updated.replace(OLD_NAME, args.name)
        if updated != text:
            changed.append(path)
            if not args.dry_run:
                path.write_text(updated)

    if not args.dry_run:
        shutil.move(str(old_dir), str(new_dir))

    for path in changed:
        print(f"rewrote {path.relative_to(REPO_ROOT)}")
    if args.dry_run:
        print(f"\nwould move src/{OLD_PACKAGE} -> src/{args.package}")
        return

    print(f"\nmoved src/{OLD_PACKAGE} -> src/{args.package}")
    print(
        "\nNext:\n"
        "  uv lock && uv sync\n"
        "  uv run pytest -q\n"
        "  uv run mcpserver  # or your new console script name (pyproject.toml)"
    )
    if subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, capture_output=True).returncode == 0:
        print("\nFiles git sees as changed are listed above; the README prose is yours to edit.")


if __name__ == "__main__":
    main()
