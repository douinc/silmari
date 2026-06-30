# SPDX-FileCopyrightText: 2026 Dou Inc.
# SPDX-License-Identifier: AGPL-3.0-or-later
from silmari_core.sensitive import NoFilter, RegexFilter


def test_regex_redacts_email() -> None:
    assert RegexFilter().redact("contact a.b+x@mail.example.com now") == "contact [EMAIL] now"


def test_regex_redacts_ssn() -> None:
    assert RegexFilter().redact("ssn 123-45-6789 ok") == "ssn [SSN] ok"


def test_regex_redacts_card() -> None:
    assert "[CARD]" in RegexFilter().redact("card 4111 1111 1111 1111")


def test_no_filter_passthrough() -> None:
    assert NoFilter().redact("a@b.com") == "a@b.com"
