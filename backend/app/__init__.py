"""Compatibility package that exposes backend/src/app when running from backend/."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent / "src" / "app")]