from __future__ import annotations

import pytest

from labs.sql_guard import inject_row_filter, is_safe_select


def test_sql_guard_rejects_writes_and_multiple_statements() -> None:
    assert is_safe_select("SELECT id FROM payments")
    assert not is_safe_select("SELECT id FROM payments; DELETE FROM payments")
    assert not is_safe_select("DELETE FROM payments")
    assert not is_safe_select("SELECT * FROM payments FOR UPDATE")
    assert not is_safe_select("SELECT * INTO OUTFILE '/tmp/x' FROM payments")


def test_row_filter_preserves_existing_where_and_alias() -> None:
    sql = inject_row_filter("SELECT p.id FROM payments AS p WHERE p.amount > 100", 42)
    assert "p.tenant_id = 42" in sql
    assert "p.amount > 100" in sql
    with pytest.raises(ValueError):
        inject_row_filter("SELECT * FROM payments JOIN customers ON payments.tenant_id=customers.tenant_id", 42)
