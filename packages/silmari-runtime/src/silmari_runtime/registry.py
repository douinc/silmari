"""Bot registry: load bots from a directory tree of ``<bot_id>/manifest.yaml`` + ``pipeline.py``.

The pipeline module is imported by path; it is pre-registered in ``sys.modules`` before execution
so that dataclasses defined inside it resolve their ``__module__`` correctly.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .manifest import BotManifest


@dataclass
class BotRecord:
    manifest: BotManifest
    run: Callable[..., Any]  # run(context: Context) -> BotResult
    path: Path


def _load_pipeline(pipeline_path: Path, bot_id: str) -> Callable[..., Any]:
    module_name = f"silmari_bot_{bot_id.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, pipeline_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load pipeline at {pipeline_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # pre-register so in-module dataclasses resolve __module__
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if not callable(run):
        raise AttributeError(f"pipeline {pipeline_path} has no run(context) function")
    return run


def load_bot(bot_dir: str | Path) -> BotRecord:
    bot_dir = Path(bot_dir)
    with open(bot_dir / "manifest.yaml") as fh:
        manifest = BotManifest.model_validate(yaml.safe_load(fh))
    run = _load_pipeline(bot_dir / "pipeline.py", manifest.bot_id)
    return BotRecord(manifest=manifest, run=run, path=bot_dir)


def load_registry(bots_dir: str | Path) -> dict[str, BotRecord]:
    bots_dir = Path(bots_dir)
    registry: dict[str, BotRecord] = {}
    for child in sorted(bots_dir.iterdir()):
        if (child / "manifest.yaml").exists():
            record = load_bot(child)
            registry[record.manifest.bot_id] = record
    return registry
