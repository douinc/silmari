"""Minimal CLI: ``silmari run <bot_id>``. Expanded in a later milestone (demo / new-bot / serve)."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from silmari_core import connect

from .executor import run_bot
from .registry import load_registry
from .store import ResultStore


def _demo_source_url() -> str:
    """Seed a throwaway DuckDB with the demo schema so `silmari run example-signal` just works."""
    import duckdb

    path = str(Path(tempfile.mkdtemp(prefix="silmari-")) / "demo.duckdb")
    con = duckdb.connect(path)
    con.execute("CREATE TABLE orders(id INTEGER, total INTEGER)")
    con.execute("INSERT INTO orders VALUES (1, 100), (2, 50)")
    con.close()
    return f"duckdb:///{path}"


def _run(args: argparse.Namespace) -> int:
    registry = load_registry(args.bots_dir)
    if args.bot_id not in registry:
        print(f"unknown bot: {args.bot_id} (available: {sorted(registry)})", file=sys.stderr)
        return 1
    source = connect(args.source or _demo_source_url())
    store = ResultStore(args.store)
    run = run_bot(registry[args.bot_id], source, store, trigger="manual")
    print(f"run {run.run_id}: {run.status} — {len(run.data)} signal(s)")
    if run.summary:
        print(run.summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="silmari")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="run a bot once and store its signals")
    run_p.add_argument("bot_id")
    run_p.add_argument("--bots-dir", default="bots")
    run_p.add_argument("--source", default=None, help="data source URL (default: seeded demo)")
    run_p.add_argument("--store", default="sqlite://", help="result store URL")
    run_p.set_defaults(func=_run)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
