# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

from silmari_runtime.cli import main

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bots"


def test_cli_run_example(capsys) -> None:
    rc = main(["run", "example-signal", "--bots-dir", str(EXAMPLES)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 signal" in out


def test_cli_unknown_bot(capsys) -> None:
    rc = main(["run", "nope", "--bots-dir", str(EXAMPLES)])
    assert rc == 1


def test_cli_run_bad_source_is_clean_error(tmp_path, capsys) -> None:
    missing = tmp_path / "nope" / "x.sqlite"  # parent dir does not exist -> cannot open read-only
    rc = main(
        ["run", "example-signal", "--bots-dir", str(EXAMPLES), "--source", f"sqlite:///{missing}"]
    )
    assert rc == 1
    assert "could not open data source" in capsys.readouterr().err  # clean message, not a traceback
