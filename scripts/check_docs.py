#!/usr/bin/env python3


from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAINTAINED_ROOT_FILES = (
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
)
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def maintained_documents(root: Path = PROJECT_ROOT) -> list[Path]:

    documents = [root / name for name in MAINTAINED_ROOT_FILES]
    documents.extend(sorted((root / "docs").rglob("*.md")))
    return documents


def validate_documentation(root: Path = PROJECT_ROOT) -> list[str]:

    errors: list[str] = []
    documents = maintained_documents(root)
    index = root / "docs" / "README.md"

    for document in documents:
        if not document.is_file():
            errors.append(f"missing maintained document: {document.relative_to(root)}")
            continue

        text = document.read_text(encoding="utf-8")
        if not text.startswith("# "):
            errors.append(f"{document.relative_to(root)}: missing level-one title")

        for raw_target in LINK_PATTERN.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            relative_target = unquote(target.split("#", 1)[0])
            resolved = (document.parent / relative_target).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                errors.append(f"{document.relative_to(root)}: link escapes project: {target}")
                continue
            if not resolved.exists():
                errors.append(f"{document.relative_to(root)}: broken local link: {target}")

    if index.is_file():
        index_text = index.read_text(encoding="utf-8")
        for document in documents:
            if document in {index, *(root / name for name in MAINTAINED_ROOT_FILES)}:
                continue
            relative = document.relative_to(index.parent).as_posix()
            if relative not in index_text and document.parent == root / "docs":
                errors.append(f"docs/README.md: document is not indexed: {relative}")

    return errors


def main() -> int:

    errors = validate_documentation()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Documentation validation passed ({len(maintained_documents())} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
