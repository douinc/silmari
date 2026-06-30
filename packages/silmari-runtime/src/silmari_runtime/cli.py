# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Silmari CLI: ``run`` a bot, ``new-bot`` to scaffold one, ``serve`` the API, ``demo``."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from silmari_core import connect

from .executor import run_bot
from .registry import load_registry
from .store import ResultStore


def _demo_source() -> tuple[str, str]:
    """Seed a throwaway DuckDB with the demo schema; returns (url, tmpdir) so it can be removed."""
    import duckdb

    tmpdir = tempfile.mkdtemp(prefix="silmari-")
    path = str(Path(tmpdir) / "demo.duckdb")
    con = duckdb.connect(path)
    con.execute("CREATE TABLE orders(id INTEGER, total INTEGER)")
    con.execute("INSERT INTO orders VALUES (1, 100), (2, 50)")
    con.execute(
        "CREATE TABLE metrics(host VARCHAR, cpu INTEGER, throughput INTEGER, "
        "throughput_baseline INTEGER, status_text VARCHAR)"
    )
    con.execute(
        "INSERT INTO metrics VALUES ('web-1', 95, 40, 100, 'ok'), "
        "('web-2', 40, 95, 100, 'request timeout')"
    )
    con.close()
    return f"duckdb:///{path}", tmpdir


def _demo_authoring_llm():
    """The offline authoring-demo 'model' — deterministic, routes the user's ask to an example bot
    over the seeded demo tables. Not a real LLM (see agent/demo.py); wire local/* for a live agent.
    """
    from .agent.demo import DemoAuthoringLLM

    return DemoAuthoringLLM()


def _run(args: argparse.Namespace) -> int:
    registry = load_registry(args.bots_dir)
    if args.bot_id not in registry:
        print(f"unknown bot: {args.bot_id} (available: {sorted(registry)})", file=sys.stderr)
        return 1
    demo_dir: str | None = None
    source = None
    try:
        if args.source is None:
            source_url, demo_dir = _demo_source()
        else:
            source_url = args.source
        try:
            source = connect(source_url)
        except Exception as exc:  # noqa: BLE001 — a bad source is user error; show it, not a traceback
            print(f"error: could not open data source {source_url!r}: {exc}", file=sys.stderr)
            return 1
        store = ResultStore(args.store)
        run = run_bot(registry[args.bot_id], source, store, trigger="manual")
        print(f"run {run.run_id}: {run.status} — {len(run.data)} signal(s)")
        if run.summary:
            print(run.summary)
        return 0
    finally:
        if source is not None:
            source.close()
        if demo_dir:
            shutil.rmtree(demo_dir, ignore_errors=True)


def _new_bot(args: argparse.Namespace) -> int:
    from .scaffold import create_bot

    try:
        path = create_bot(args.bot_id, kind=args.kind, name=args.name, bots_dir=args.bots_dir)
    except (ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"created {path}")
    return 0


def _serve(args: argparse.Namespace) -> int:  # pragma: no cover - blocking server
    import uvicorn

    from .api.app import create_app

    source = None
    demo_dir = None
    authoring_llm = None
    try:
        if args.source:
            try:
                source = connect(args.source)
            except Exception as exc:  # noqa: BLE001 — a bad source is user error; show it cleanly
                print(f"error: could not open data source {args.source!r}: {exc}", file=sys.stderr)
                return 1
        elif args.demo_data:
            url, demo_dir = _demo_source()
            source = connect(url)
            authoring_llm = _demo_authoring_llm()
        app = create_app(
            bots_dir=args.bots_dir,
            store=ResultStore(args.store),
            source=source,
            ui_dir=args.ui,
            authoring_llm=authoring_llm,
        )
        uvicorn.run(app, host=args.host, port=args.port)
    finally:
        if source is not None:
            source.close()
        if demo_dir is not None:
            shutil.rmtree(demo_dir, ignore_errors=True)
    return 0


_DEMO_RULESET = {
    "id_field": "host",
    "rules": [
        {
            "rule_id": 1,
            "label": "high_cpu",
            "conditions": {"criteria": [{"field": "cpu", "operator": "gt", "value": 90}]},
        },
        {
            "rule_id": 2,
            "label": "status_timeout",
            "conditions": {
                "criteria": [
                    {"field": "status_text", "operator": "text_present", "value": "timeout"}
                ]
            },
        },
    ],
}


def _demo(args: argparse.Namespace) -> int:
    from .ruleset import evaluate, validate_ruleset

    source = None
    tmpdir = None
    try:
        url, tmpdir = _demo_source()
        source = connect(url)
        rows = source.query("SELECT * FROM metrics")
        report = validate_ruleset(_DEMO_RULESET)
        if report.doc is None:
            print("demo ruleset is invalid", file=sys.stderr)
            return 1
        signals = evaluate(report.doc, rows)
        print(f"Silmari demo — {len(signals)} review-priority signal(s) from {len(rows)} rows:")
        for sig in signals:
            print(f"  - {sig.target_id}: {sig.label}  [{sig.note}]")
        return 0
    finally:
        if source is not None:
            source.close()
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="silmari")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run a bot once and store its signals")
    run_p.add_argument("bot_id")
    run_p.add_argument("--bots-dir", default="bots")
    run_p.add_argument("--source", default=None, help="data source URL (default: seeded demo)")
    run_p.add_argument("--store", default="sqlite://", help="result store URL")
    run_p.set_defaults(func=_run)

    new_p = sub.add_parser("new-bot", help="scaffold a new bot")
    new_p.add_argument("bot_id")
    new_p.add_argument("--kind", default="signal", choices=["signal", "prediction"])
    new_p.add_argument("--name", default=None)
    new_p.add_argument("--bots-dir", default="bots")
    new_p.set_defaults(func=_new_bot)

    serve_p = sub.add_parser("serve", help="serve the HTTP API (uvicorn)")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.add_argument("--bots-dir", default="bots")
    serve_p.add_argument("--source", default=None)
    serve_p.add_argument("--store", default="sqlite://")
    serve_p.add_argument(
        "--ui", nargs="?", const="examples/frontend", default=None,
        help="serve a static reference UI directory (default: examples/frontend)",
    )
    serve_p.add_argument(
        "--demo-data", action="store_true",
        help="seed a throwaway demo source (orders/metrics) when --source is not given",
    )
    serve_p.set_defaults(func=_serve)

    demo_p = sub.add_parser("demo", help="run a self-contained ruleset demo")
    demo_p.set_defaults(func=_demo)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
