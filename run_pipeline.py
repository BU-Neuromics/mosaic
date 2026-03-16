#!/usr/bin/env python3
"""Hippo implementation pipeline.
Wraps openplan implement with the correct project layout:
  - openplan/ lives in hippo/plan/
  - openspec/ and src/ live in hippo/
  - ACP sessions run with cwd=hippo/ so OpenSpec slash commands work
"""
import sys, subprocess, yaml
from pathlib import Path

HIPPO_DIR = Path(__file__).parent
PLAN_DIR = HIPPO_DIR / "plan"

# Temporarily symlink plan/openplan into hippo/ so openplan CLI finds it,
# then run implement with project_dir=hippo/
import os, shutil

openplan_link = HIPPO_DIR / "openplan"
if not openplan_link.exists():
    openplan_link.symlink_to(PLAN_DIR / "openplan")

try:
    cmd = [
        "uv", "--project", "/home/admin/.openclaw/workspace/openplan",
        "run", "openplan", "implement",
        "--skip-tests",
        "--model", "ollama/qwen3-coder:30b",
    ] + sys.argv[1:]
    subprocess.run(cmd, cwd=str(HIPPO_DIR), check=True)
finally:
    if openplan_link.is_symlink():
        openplan_link.unlink()
