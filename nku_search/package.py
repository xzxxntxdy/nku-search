from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import zipfile


ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    ".uv-cache",
    ".npm-cache",
    "__pycache__",
    ".pytest_cache",
    "data",
    "elasticsearch-data",
    "references",
    "node_modules",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".zip", ".rar", ".db", ".log", ".tsbuildinfo"}


def should_include(path: Path) -> bool:
    relative_parts = path.relative_to(ROOT).parts
    if relative_parts[0] == "dist":
        return False
    if any(part in EXCLUDE_DIRS for part in relative_parts):
        return False
    return path.suffix not in EXCLUDE_SUFFIXES


def build_package(name: str) -> Path:
    dist_dir = ROOT / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    code_dir = dist_dir / name / "代码"
    docs_dir = dist_dir / name / "说明文档"
    video_dir = dist_dir / name / "演示视频"
    code_dir.mkdir(parents=True)
    docs_dir.mkdir(parents=True)
    video_dir.mkdir(parents=True)

    for path in ROOT.rglob("*"):
        if not path.is_file() or not should_include(path):
            continue
        rel = path.relative_to(ROOT)
        if rel.parts[0] == "docs":
            target = docs_dir / Path(*rel.parts[1:])
        elif rel.parts[0] == "dist":
            continue
        else:
            target = code_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    (video_dir / "README.txt").write_text(
        "请将最终录制的不超过 15 分钟演示视频放在本目录。\n可参考说明文档中的 docs/演示视频脚本.md。\n",
        encoding="utf-8",
    )

    zip_path = ROOT / f"{name}_hw4.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (dist_dir / name).rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(dist_dir))
    return zip_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package homework submission.")
    parser.add_argument("--name", default="2412235_匡航逸", help="Student id and name prefix.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    zip_path = build_package(args.name)
    print(f"Created {zip_path}")


if __name__ == "__main__":
    main()
