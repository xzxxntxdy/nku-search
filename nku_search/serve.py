from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_DIST_INDEX = FRONTEND_DIR / "dist" / "index.html"


def _latest_mtime(paths: list[Path]) -> float:
    latest = 0.0
    for path in paths:
        if path.is_file():
            latest = max(latest, path.stat().st_mtime)
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and "node_modules" not in child.parts and "dist" not in child.parts:
                    latest = max(latest, child.stat().st_mtime)
    return latest


def frontend_build_required() -> bool:
    if not FRONTEND_DIR.exists():
        return False
    if not FRONTEND_DIST_INDEX.exists():
        return True
    source_paths = [
        FRONTEND_DIR / "src",
        FRONTEND_DIR / "package.json",
        FRONTEND_DIR / "package-lock.json",
        FRONTEND_DIR / "index.html",
        FRONTEND_DIR / "vite.config.ts",
        FRONTEND_DIR / "tsconfig.json",
        FRONTEND_DIR / "tsconfig.app.json",
    ]
    return _latest_mtime(source_paths) > FRONTEND_DIST_INDEX.stat().st_mtime


def ensure_frontend_build() -> None:
    if not frontend_build_required():
        return
    npm = "npm.cmd" if os.name == "nt" else "npm"
    print("Frontend build is stale; running npm run build...", flush=True)
    try:
        subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True)
    except FileNotFoundError as exc:
        raise SystemExit("npm was not found. Install Node.js or run the frontend build manually.") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"frontend build failed with exit code {exc.returncode}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NKU search web service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--skip-frontend-build", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.skip_frontend_build:
        ensure_frontend_build()
    import uvicorn

    uvicorn.run("nku_search.web:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
