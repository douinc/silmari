# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
def test_workspace_imports() -> None:
    import silmari_core
    import silmari_runtime

    assert silmari_core.__version__
    assert silmari_runtime.__version__
