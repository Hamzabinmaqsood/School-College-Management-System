#!/usr/bin/env python3
"""Create an allowlisted customer source and browser bundle."""

import argparse
import re
import zipfile
from pathlib import Path

KEY_MARKER = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|openssh-key-v1\x00")
ASSET_SUFFIXES = {
    ".html",
    ".js",
    ".css",
    ".json",
    ".txt",
    ".woff",
    ".woff2",
    ".ico",
    ".png",
    ".svg",
}


def candidates(root):
    for folder in ("backend/apps", "backend/config"):
        yield from (
            path
            for path in (root / folder).rglob("*.py")
            if not any(
                part.startswith(".") or part == "__pycache__"
                for part in path.relative_to(root).parts
            )
        )
    for name in (
        "backend/manage.py",
        "backend/.env.example",
        "backend/requirements/production.txt",
        "docs/DEPLOYMENT.md",
        "docs/LICENSING.md",
    ):
        yield root / name
    notices = root / "frontend/dist/school/3rdpartylicenses.txt"
    if notices.is_file():
        yield notices
    for path in (root / "frontend/dist/school/browser").rglob("*"):
        if (
            path.is_file()
            and path.suffix in ASSET_SUFFIXES
            and not any(part.startswith(".") for part in path.relative_to(root).parts)
        ):
            yield path


def stage(root):
    if not (root / "frontend/dist/school/browser/index.html").is_file():
        raise ValueError("Build the Angular production application first.")
    files = {}
    for path in candidates(root):
        relative = path.relative_to(root)
        if path.resolve() != path or not path.is_file():
            raise ValueError(f"Package input is missing or a symlink: {relative}")
        data = path.read_bytes()
        if KEY_MARKER.search(data):
            raise ValueError(f"Private key material detected in {relative}")
        files[relative.as_posix()] = data
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        files = stage(Path(__file__).resolve().parents[1])
        with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, data in sorted(files.items()):
                archive.writestr(path, data)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Customer packaging failed: {exc}\n")
    print(f"Customer package created with {len(files)} allowlisted files.")


if __name__ == "__main__":
    main()
