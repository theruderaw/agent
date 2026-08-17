"""
tests/skills/test_loader.py
"""

import pytest
from pathlib import Path

from app.skills.loader import (
    SkillLoader,
    SkillNotFoundError,
    InvalidSkillNameError,
)


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "docs"
    d.mkdir()
    (d / "summarize.md").write_text("# Summarize\n\nInstructions here.")
    (d / "research.md").write_text("# Research\n\nDo research.")
    return d


@pytest.fixture
def loader(skills_dir: Path) -> SkillLoader:
    return SkillLoader(skills_dir)


class TestLoad:
    def test_load_existing_skill(self, loader: SkillLoader):
        skill = loader.load("summarize")
        assert skill.name == "summarize"
        assert "Instructions here." in skill.content

    def test_load_missing_skill_raises(self, loader: SkillLoader):
        with pytest.raises(SkillNotFoundError):
            loader.load("does_not_exist")

    def test_load_missing_skill_error_mentions_name(self, loader: SkillLoader):
        with pytest.raises(SkillNotFoundError, match="ghost"):
            loader.load("ghost")


class TestNameValidation:
    @pytest.mark.parametrize(
        "bad_name",
        [
            "../secrets",
            "../../etc/passwd",
            "/etc/passwd",
            "foo/bar",
            "foo.md",  # extension should not be included by caller
            "",
            "foo bar",
            "foo\x00bar",
        ],
    )
    def test_invalid_names_rejected(self, loader: SkillLoader, bad_name: str):
        with pytest.raises(InvalidSkillNameError):
            loader.load(bad_name)

    def test_valid_names_allowed(self, loader: SkillLoader):
        # hyphen and underscore both fine
        assert loader.exists("summarize") is True


class TestExists:
    def test_exists_true_for_present_skill(self, loader: SkillLoader):
        assert loader.exists("research") is True

    def test_exists_false_for_missing_skill(self, loader: SkillLoader):
        assert loader.exists("nope") is False

    def test_exists_false_for_invalid_name_does_not_raise(self, loader: SkillLoader):
        assert loader.exists("../nope") is False


class TestListAvailable:
    def test_lists_all_skills(self, loader: SkillLoader):
        assert loader.list_available() == ["research", "summarize"]

    def test_empty_dir_returns_empty_list(self, tmp_path: Path):
        empty = tmp_path / "empty_docs"
        empty.mkdir()
        loader = SkillLoader(empty)
        assert loader.list_available() == []

    def test_nonexistent_dir_returns_empty_list(self, tmp_path: Path):
        loader = SkillLoader(tmp_path / "does_not_exist")
        assert loader.list_available() == []