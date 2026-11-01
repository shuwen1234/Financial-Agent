from __future__ import annotations

from dataclasses import dataclass

from unidiff import PatchSet


@dataclass(frozen=True)
class AddedLine:
    file: str
    line: int
    text: str


def parse_added_lines(diff: str) -> list[AddedLine]:
    result: list[AddedLine] = []
    for changed_file in PatchSet(diff.splitlines(keepends=True)):
        if changed_file.is_removed_file:
            continue
        for hunk in changed_file:
            for line in hunk:
                if line.is_added and line.target_line_no is not None:
                    result.append(AddedLine(changed_file.path.replace("\\", "/"), line.target_line_no, line.value.rstrip("\n")))
    return result
