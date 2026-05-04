"""
ai_patch_apply_launch.pyw  —  QiGor Wallpaper Manager  patch launcher
======================================================================
Run this to apply AI-generated patch zips or build a combined source zip.

  python ai_patch_apply_launch.pyw

The target_map tells the patcher which top-level folder inside the zip
maps to which directory on disk:

  qigor_wallpaper/app      ->  app/          (the Python package)
  qigor_wallpaper/assets   ->  assets/       (images)
  qigor_wallpaper/root     ->  ./            (entry point .pyw, build scripts)

AI: when producing a patch zip, use this folder structure at the top level:
  app/
    constants.py
    config.py
    ...
  assets/
    ...
  root/
    qigor_wallpaper_manager.pyw
    build.py
    ...
"""
from __future__ import annotations
import sys
from pathlib import Path

AI_PATCH_APPLY_PYW = Path(r"C:\Users\my4nt\OneDrive - Early Buddhism Meditation Preservation Society\lucid24\py_tools\ai_patch\ai_patch_apply.pyw")

PROJECT_ROOT = Path(__file__).parent.resolve()

CONFIG = {
    "project_name":     "QiGor Wallpaper Manager",
    "project_root":     PROJECT_ROOT,
    "downloads_dir":    Path.home() / "Downloads",
    "zip_output_dir":   PROJECT_ROOT,
    "zip_description":  "source bundle",
    "open_after_build": True,
    "target_map": {
        "app":    PROJECT_ROOT / "app",
        "assets": PROJECT_ROOT / "assets",
        "root":   PROJECT_ROOT,
    },
}

def _find_tool() -> Path:
    if AI_PATCH_APPLY_PYW.exists():
        return AI_PATCH_APPLY_PYW
    sibling = Path(__file__).parent / "ai_patch_apply.pyw"
    if sibling.exists():
        return sibling
    raise FileNotFoundError(
        f"ai_patch_apply.pyw not found.\n"
        f"Checked:\n  {AI_PATCH_APPLY_PYW}\n  {sibling}\n\n"
        f"Edit AI_PATCH_APPLY_PYW at the top of this file."
    )

if __name__ == "__main__":
    tool = _find_tool()
    sys.path.insert(0, str(tool.parent))
    from ai_patch_apply import run_app
    run_app(CONFIG)
