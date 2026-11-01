from __future__ import annotations

from eval.run_offline import run


def test_golden_citations_and_refusal() -> None:
    rows = run(top_k=3)
    positives = [row for row in rows if not row["should_refuse"]]
    negatives = [row for row in rows if row["should_refuse"]]
    assert len(positives) == 8 and len(negatives) == 2
    assert all(row["citation_hit"] and row["answer_contains"] for row in positives)
    assert all(row["refusal_correct"] for row in negatives)
