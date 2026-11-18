# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""The no-PyYAML frontmatter fallback must agree with PyYAML on the repo's own skills."""

from pathlib import Path

import pytest

from commerce_common import skills

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    p for p in ROOT.rglob("SKILL.md") if "node_modules" not in p.parts and ".venv" not in p.parts
]


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_fallback_matches_pyyaml(path, monkeypatch):
    text = path.read_text(encoding="utf-8")
    with_yaml = skills.parse_skill_md(text, path)
    monkeypatch.setattr(skills, "yaml", None)
    assert skills.parse_skill_md(text, path) == with_yaml
