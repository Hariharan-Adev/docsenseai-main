"""Compatibility package that exposes the root db layer from backend commands."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[2] / "db")]