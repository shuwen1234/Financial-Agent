# Text2SQL 练习用 MSchema（虚构表）

```text
# Table: contracts
[(id:INT, 主键), (tenant_id:INT, 租户), (customer_id:INT, 客户), (effective_date:DATE, 合同生效日)]

# Table: customers
[(id:INT, 主键), (tenant_id:INT, 租户), (name:VARCHAR, 客户名称)]

# Table: payments
[(id:INT, 主键), (tenant_id:INT, 租户), (contract_id:INT, 合同), (amount:DECIMAL, 金额), (paid_at:DATETIME, 支付时间)]
```

DDL 主要告诉数据库如何建表；此处的 MSchema 摘要面向模型，额外给出字段含义。`labs/sql_guard.py` 只演示单表租户条件，复杂 JOIN 权限应由经过验证的 SQL 模板或数据库行级策略负责。
