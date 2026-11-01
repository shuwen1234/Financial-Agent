"""独立 Text2SQL 安全实验；不能替代数据库只读账号与资源限制。"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"contracts", "customers", "payments"}
FORBIDDEN = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Merge, exp.Command, exp.Into)


def is_safe_select(sql: str) -> bool:
    try:
        statements = [statement for statement in sqlglot.parse(sql, read="mysql") if statement is not None]
    except sqlglot.errors.ParseError:
        return False
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return False
    root = statements[0]
    if root.args.get("locks") or root.args.get("into"):
        return False
    return not any(isinstance(node, FORBIDDEN) for node in root.walk())


def inject_row_filter(sql: str, tenant_id: int) -> str:
    if not is_safe_select(sql):
        raise ValueError("只允许单条只读 SELECT")
    if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id < 0:
        raise ValueError("tenant_id 必须是非负整数")
    tree = sqlglot.parse_one(sql, read="mysql")
    tables = list(tree.find_all(exp.Table))
    if len(tables) != 1 or tree.args.get("joins") or tree.args.get("with"):
        raise ValueError("练习版只支持单表，无 JOIN/CTE/子查询")
    if tables[0].name not in ALLOWED_TABLES:
        raise ValueError("表未获准访问")
    qualifier = tables[0].alias_or_name
    condition = exp.EQ(this=exp.column("tenant_id", table=qualifier), expression=exp.Literal.number(tenant_id))
    return tree.where(condition).sql(dialect="mysql")


if __name__ == "__main__":
    samples = [
        "SELECT id, amount FROM payments WHERE amount > 100",
        "SELECT * FROM payments; DELETE FROM payments",
        "DELETE FROM payments",
        "SELECT * FROM payments FOR UPDATE",
    ]
    for sample in samples:
        print(is_safe_select(sample), sample)
    print(inject_row_filter(samples[0], 42))
