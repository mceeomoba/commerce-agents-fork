# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Skill loading. A skill is a directory holding ``SKILL.md``: YAML frontmatter with
``name`` and ``description``, then the instructions. The static prompt carries the index
and ``load_skill`` returns a body on demand.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:  # PyYAML needs a build step some hosts (Android) cannot do; a small fallback covers it.
    import yaml
except ImportError:  # pragma: no cover - exercised by tests through _simple_frontmatter
    yaml = None


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str


class SkillLoadError(ValueError):
    pass


def _simple_frontmatter(text: str) -> dict:
    """Flat `key: value` frontmatter with optional quotes and indented continuation lines."""
    meta: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[0] in " \t" and key:
            meta[key] = f"{meta[key]} {line.strip()}".strip()
            continue
        name, sep, value = line.partition(":")
        if not sep:
            continue
        key = name.strip()
        value = value.strip()
        if value[:1] in "|>":
            value = ""
        elif len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key] = value
    return meta


def parse_skill_md(text: str, path: Path | None = None) -> Skill:
    if not text.startswith("---"):
        raise SkillLoadError(f"{path or 'SKILL.md'}: missing YAML frontmatter")
    try:
        _, frontmatter, body = text.split("---", 2)
    except ValueError as exc:
        raise SkillLoadError(f"{path or 'SKILL.md'}: malformed frontmatter fences") from exc
    meta = (yaml.safe_load(frontmatter) if yaml else _simple_frontmatter(frontmatter)) or {}
    name = meta.get("name")
    description = meta.get("description")
    if not name or not description:
        raise SkillLoadError(f"{path or 'SKILL.md'}: frontmatter needs `name` and `description`")
    return Skill(name=str(name), description=str(description).strip(), body=body.strip())


def load_skill_dir(skill_dir: Path) -> Skill:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise SkillLoadError(f"{skill_dir}: no SKILL.md found")
    return parse_skill_md(skill_md.read_text(encoding="utf-8"), path=skill_md)


def load_skills(skills_root: Path) -> list[Skill]:
    """Every skill directory under ``skills_root``; names must be unique."""
    skills = [
        load_skill_dir(child)
        for child in sorted(skills_root.iterdir())
        if child.is_dir() and (child / "SKILL.md").exists()
    ]
    names = [skill.name for skill in skills]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise SkillLoadError(f"duplicate skill names: {sorted(duplicates)}")
    return skills


class SkillRegistry:
    """The loaded skills, sorted by name so the index renders the same bytes every time."""

    def __init__(self, skills: list[Skill]):
        self._skills = sorted(skills, key=lambda skill: skill.name)
        self._by_name = {skill.name: skill for skill in self._skills}

    @classmethod
    def from_dir(cls, skills_root: Path) -> SkillRegistry:
        return cls(load_skills(skills_root))

    @property
    def names(self) -> list[str]:
        return [skill.name for skill in self._skills]

    def index_block(self) -> str:
        if not self._skills:
            return "(no skills installed)"
        return "\n".join(f"- `{skill.name}` — {skill.description}" for skill in self._skills)

    def get_instructions(self, name: str) -> str | None:
        skill = self._by_name.get(name)
        return None if skill is None else skill.body
