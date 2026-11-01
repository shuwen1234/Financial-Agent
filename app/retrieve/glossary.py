"""可审查的术语归一表；只改检索词，保留原问题用于回答。"""
from __future__ import annotations

GLOSSARY = {
    "提前还钱": "提前还款",
    "提前结清": "提前还款",
    "还清贷款": "提前还款",
    "罚款": "违约责任",
    "违约金": "违约责任",
    "合同到期": "合同终止",
    "监管规定": "合规要求",
    "客户身份核查": "客户身份识别",
    "反洗钱核验": "反洗钱审查",
    "销户": "账户注销",
}


def normalize_query(query: str) -> str:
    result = query.strip()
    for variant in sorted(GLOSSARY, key=len, reverse=True):
        result = result.replace(variant, GLOSSARY[variant])
    return result
