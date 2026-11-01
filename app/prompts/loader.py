from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

from app.config import PROJECT_ROOT


@dataclass(frozen=True)
class PromptSpec:
    name: str
    version: str
    variables: tuple[str, ...]
    system: str
    user: str


class PromptRegistry:
    def __init__(self, root: Path = PROJECT_ROOT / "prompts"):
        self.root = root
        self._cache: dict[Path, tuple[int, PromptSpec]] = {}
        self._jinja = Environment(undefined=StrictUndefined, autoescape=False)

    def load(self, name: str, version: str) -> PromptSpec:
        if not name.replace("_", "").isalnum() or not version.replace("_", "").isalnum():
            raise ValueError("无效的 Prompt 名称或版本")
        path = self.root / name / f"{version}.yaml"
        mtime = path.stat().st_mtime_ns
        cached = self._cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("name") != name or raw.get("version") != version:
            raise ValueError("Prompt 元数据与路径不一致")
        variables = raw.get("variables")
        if not isinstance(variables, list) or not all(isinstance(v, str) for v in variables):
            raise TypeError("Prompt variables 必须是字符串列表")
        if not isinstance(raw.get("system"), str) or not isinstance(raw.get("user"), str):
            raise TypeError("Prompt 必须含 system 和 user 模板")
        spec = PromptSpec(name, version, tuple(variables), raw["system"], raw["user"])
        self._cache[path] = (mtime, spec)
        return spec

    def render(self, name: str, version: str, **variables: str) -> tuple[str, str]:
        spec = self.load(name, version)
        if set(variables) != set(spec.variables):
            raise ValueError(f"Prompt 变量必须是 {spec.variables}")
        return (
            self._jinja.from_string(spec.system).render(**variables),
            self._jinja.from_string(spec.user).render(**variables),
        )
