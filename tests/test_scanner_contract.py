"""Every registered scanner must honour the contract in adding-scanners.md."""

from __future__ import annotations

import inspect

import pytest

from core.interfaces.scanner import OSINTScanner
from core.services.identity_pipeline import _EMAIL_SCANNERS, _USERNAME_SCANNERS

ALL_SCANNERS = (*_USERNAME_SCANNERS, *_EMAIL_SCANNERS)


@pytest.mark.parametrize("scanner_class", ALL_SCANNERS, ids=lambda c: c.__name__)
def test_scanner_implements_the_protocol(scanner_class):
    scanner = scanner_class()
    assert isinstance(scanner, OSINTScanner)
    # An inherited Protocol method would return None and break deduplication.
    assert scanner_class.scan is not OSINTScanner.scan
    assert inspect.iscoroutinefunction(scanner_class.scan)


def test_documented_counts_match_the_registry():
    assert (len(_USERNAME_SCANNERS), len(_EMAIL_SCANNERS)) == (20, 4)
