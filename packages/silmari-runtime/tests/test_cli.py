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
