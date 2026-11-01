from __future__ import annotations

from pathlib import Path

from labs.review.diff_parser import parse_added_lines
from labs.review.reviewer import review


def test_diff_review_reports_only_added_line() -> None:
    diff = (Path(__file__).resolve().parents[1] / "labs" / "review" / "sample.diff").read_text(encoding="utf-8")
    added = parse_added_lines(diff)
    assert added[0].file == "labs/review/fixtures/bad.py" and added[0].line == 1
    report = review(diff)
    assert any(item.line == 1 and "F401" in item.issue and item.source == "ruff" for item in report.findings)
