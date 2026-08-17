from __future__ import annotations

import argparse
import fnmatch
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "clean_site_template"

EXCLUDE_PATTERNS = [
    ".git",
    ".git/**",
    ".agents",
    ".agents/**",
    ".codex",
    ".codex/**",
    "dist",
    "dist/**",
    "tmp",
    "tmp/**",
    "outputs",
    "outputs/**",
    "**/node_modules",
    "**/node_modules/**",
    "**/__pycache__",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.db",
    "**/*.sqlite",
    "**/*.sqlite3",
    "**/*.log",
    "**/*.bak",
    "**/*.tmp",
    "**/*.inspect.ndjson",
    ".env",
    ".env.*",
    "!/.env.example",
]


def normalize(path: Path) -> str:
    return path.as_posix()


def is_excluded(rel: Path) -> bool:
    text = normalize(rel)
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("!") and fnmatch.fnmatch(text, pattern[1:].lstrip("/")):
            return False
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("!"):
            continue
        if fnmatch.fnmatch(text, pattern):
            return True
    return False


def copy_clean_tree(output_dir: Path) -> tuple[int, int]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    file_count = 0
    total_size = 0
    for src in ROOT.rglob("*"):
        rel = src.relative_to(ROOT)
        if is_excluded(rel):
            continue
        dest = output_dir / rel
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        file_count += 1
        total_size += src.stat().st_size
    return file_count, total_size


def write_manifest(output_dir: Path, file_count: int, total_size: int) -> Path:
    manifest = output_dir / "TEMPLATE_MANIFEST.md"
    final_file_count = file_count + 1
    manifest.write_text(
        "\n".join(
            [
                "# Clean Site Template Manifest",
                "",
                f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
                f"- Source: {ROOT}",
                f"- Files included: {final_file_count}",
                f"- Approx size: {total_size / 1024 / 1024:.2f} MiB",
                "",
                "## Excluded",
                "",
                "- `tmp/` and old case-specific temporary outputs",
                "- `node_modules/` and runtime caches",
                "- `.db`, `.sqlite`, logs, backup files",
                "- `.env` files except `.env.example`",
                "- `.git`, `.agents`, `.codex` metadata",
                "",
                "## Next Step",
                "",
                "Run `tools/site_input_builder.py` in this clean template to create a new site workbook and skeleton config.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="產生乾淨的新案場模板包，排除暫存與敏感輸出。")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="輸出資料夾")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    file_count, total_size = copy_clean_tree(output_dir)
    manifest = write_manifest(output_dir, file_count, total_size)
    final_file_count = file_count + 1
    print(f"Generated: {output_dir}")
    print(f"Files: {final_file_count}")
    print(f"Size MiB: {total_size / 1024 / 1024:.2f}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
