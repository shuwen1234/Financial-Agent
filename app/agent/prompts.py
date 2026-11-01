from __future__ import annotations

from app.prompts.loader import PromptRegistry

registry = PromptRegistry()


def build_messages(question: str, evidence: list[tuple[int, str, str, int]], version: str) -> list[dict[str, str]]:
    evidence_text = "\n\n".join(
        f"[source_id={source_id}; title={title}; version={doc_version}]\n{excerpt}"
        for source_id, title, excerpt, doc_version in evidence
    )
    system, user = registry.render("answer", version, question=question, evidence=evidence_text)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
