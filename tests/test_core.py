"""Tests for app/core.py — Settings configuration."""

import os

import pytest


class TestSettings:
    def test_settings_loads_with_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///test.db")
        from app.core import Settings
        s = Settings(database_url="sqlite+aiosqlite:///test.db")
        assert s.database_url == "sqlite+aiosqlite:///test.db"

    def test_explicit_overrides(self):
        from app.core import Settings
        s = Settings(
            database_url="x",
            ollama_base_model="custom-model",
            max_iterations=10,
        )
        assert s.ollama_base_model == "custom-model"
        assert s.max_iterations == 10

    def test_extra_fields_ignored(self):
        from app.core import Settings
        s = Settings(database_url="x", extra_field="ignored")
        assert s.database_url == "x"

    def test_settings_is_singleton_on_import(self):
        from app.core import settings
        from app.core import Settings
        assert isinstance(settings, Settings)
