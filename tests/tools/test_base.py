"""Tests for app/tools/base.py — registry, dispatch, introspection, errors."""

import pytest
from pydantic import ValidationError

from app.tools.base import (
    Tool,
    ToolError,
    ToolRegistry,
    ToolRegistrationError,
    ToolResult,
    ToolValidationError,
    UnknownToolError,
    Toolkit,
    _build_args_model,
    _extract_description,
    _public_methods,
)


# ─────────────────────────────────────────────
# ToolResult
# ─────────────────────────────────────────────


class TestToolResult:
    def test_success(self):
        r = ToolResult.success({"x": 1})
        assert r.ok is True
        assert r.data == {"x": 1}
        assert r.error is None

    def test_failure(self):
        r = ToolResult.failure("boom")
        assert r.ok is False
        assert r.error == "boom"
        assert r.data is None

    def test_success_with_none_data(self):
        r = ToolResult.success(None)
        assert r.ok is True
        assert r.data is None


# ─────────────────────────────────────────────
# Error hierarchy
# ─────────────────────────────────────────────


class TestErrorHierarchy:
    def test_unknown_tool_is_tool_error(self):
        assert issubclass(UnknownToolError, ToolError)

    def test_registration_error_is_tool_error(self):
        assert issubclass(ToolRegistrationError, ToolError)

    def test_validation_error_is_tool_error(self):
        assert issubclass(ToolValidationError, ToolError)

    def test_unknown_tool_error_stores_qualified_name(self):
        e = UnknownToolError("fs:read")
        assert e.qualified_name == "fs:read"
        assert "fs:read" in str(e)

    def test_tool_validation_error_stores_fields(self):
        inner = ValidationError.from_exception_data("test", [])
        e = ToolValidationError("x:y", inner)
        assert e.qualified_name == "x:y"
        assert e.errors is inner


# ─────────────────────────────────────────────
# Tool schema
# ─────────────────────────────────────────────


class TestToolSchema:
    def _make_tool(self, skills=None):
        from pydantic import create_model

        ArgsModel = create_model("Args", path=(str, ...))
        return Tool(
            namespace="fs",
            method_name="read",
            description="read a file",
            args_model=ArgsModel,
            bound_method=lambda: None,
            skills=skills,
        )

    def test_qualified_name(self):
        t = self._make_tool()
        assert t.qualified_name == "fs:read"

    def test_schema_includes_skills_when_set(self):
        t = self._make_tool(skills="git")
        schema = t.schema()
        assert schema["skills"] == "git"

    def test_schema_excludes_skills_when_none(self):
        t = self._make_tool(skills=None)
        schema = t.schema()
        assert "skills" not in schema

    def test_schema_structure(self):
        t = self._make_tool()
        schema = t.schema()
        assert schema["name"] == "fs:read"
        assert schema["description"] == "read a file"
        assert "input_schema" in schema
        assert schema["input_schema"]["type"] == "object"


# ─────────────────────────────────────────────
# _extract_description
# ─────────────────────────────────────────────


class TestExtractDescription:
    def test_extracts_first_line(self):
        def method():
            """First line.
            Second line.
            """
        assert _extract_description(method) == "First line."

    def test_strips_whitespace(self):
        def method():
            """  indented  """
        assert _extract_description(method) == "indented"

    def test_missing_docstring_raises(self):
        def method():
            pass
        with pytest.raises(ToolRegistrationError, match="missing a docstring"):
            _extract_description(method)


# ─────────────────────────────────────────────
# _build_args_model
# ─────────────────────────────────────────────


class TestBuildArgsModel:
    def test_simple_typed_params(self):
        def method(self, path: str, count: int = 10):
            """A method."""
        model = _build_args_model("ns", "method", method)
        instance = model(path="hello", count=5)
        assert instance.path == "hello"
        assert instance.count == 5

    def test_defaults_apply(self):
        def method(self, x: int = 42):
            """Doc."""
        model = _build_args_model("ns", "method", method)
        instance = model()
        assert instance.x == 42

    def test_missing_type_hint_raises(self):
        def method(self, x):
            """Doc."""
        with pytest.raises(ToolRegistrationError, match="missing a type hint"):
            _build_args_model("ns", "method", method)

    def test_varargs_skipped(self):
        def method(self, *args, **kwargs):
            """Doc."""
        model = _build_args_model("ns", "method", method)
        assert len(model.model_fields) == 0

    def test_model_name_convention(self):
        def method(self, path: str):
            """Doc."""
        model = _build_args_model("fs", "read_path", method)
        assert model.__name__ == "FsReadPathArgs"


# ─────────────────────────────────────────────
# _public_methods
# ─────────────────────────────────────────────


class TestPublicMethods:
    def test_yields_only_public(self):
        class Obj:
            def public(self): pass
            def _private(self): pass
        obj = Obj()
        names = [n for n, _ in _public_methods(obj)]
        assert "public" in names
        assert "_private" not in names

    def test_yields_callable_methods(self):
        class Obj:
            def method(self): pass
            attr = "not a method"
        obj = Obj()
        names = [n for n, _ in _public_methods(obj)]
        assert "method" in names
        assert "attr" not in names


# ─────────────────────────────────────────────
# ToolRegistry
# ─────────────────────────────────────────────


class _GoodToolkit:
    namespace = "calc"

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        """Subtract b from a."""
        return a - b


class _NoNamespaceToolkit:
    def foo(self):
        """Do foo."""


class _BadToolkit:
    namespace = "bad"

    def no_docstring(self, x: str):
        pass


class _SkillsToolkit:
    namespace = "git"
    skills = "git"

    def status(self):
        """Git status."""
        return "ok"


class TestToolRegistryRegister:
    def test_registers_toolkit(self):
        reg = ToolRegistry()
        reg.register_toolkit(_GoodToolkit())
        assert "calc:add" in reg.list()
        assert "calc:subtract" in reg.list()

    def test_no_namespace_raises(self):
        reg = ToolRegistry()
        with pytest.raises(ToolRegistrationError, match="must define a 'namespace'"):
            reg.register_toolkit(_NoNamespaceToolkit())

    def test_duplicate_raises(self):
        reg = ToolRegistry()
        reg.register_toolkit(_GoodToolkit())
        with pytest.raises(ToolRegistrationError, match="Duplicate"):
            reg.register_toolkit(_GoodToolkit())

    def test_missing_docstring_raises(self):
        reg = ToolRegistry()
        with pytest.raises(ToolRegistrationError, match="missing a docstring"):
            reg.register_toolkit(_BadToolkit())

    def test_skills_propagated(self):
        reg = ToolRegistry()
        reg.register_toolkit(_SkillsToolkit())
        tool = reg.get("git:status")
        assert tool.skills == "git"

    def test_namespace_subclass(self):
        reg = ToolRegistry()
        reg.register_toolkit(_GoodToolkit())
        tool = reg.get("calc:add")
        assert tool.namespace == "calc"
        assert tool.method_name == "add"


class TestToolRegistryGet:
    def test_get_existing(self):
        reg = ToolRegistry()
        reg.register_toolkit(_GoodToolkit())
        tool = reg.get("calc:add")
        assert tool.method_name == "add"

    def test_get_unknown_raises(self):
        reg = ToolRegistry()
        with pytest.raises(UnknownToolError):
            reg.get("nonexistent:tool")


class TestToolRegistryList:
    def test_empty(self):
        assert ToolRegistry().list() == []

    def test_multiple(self):
        reg = ToolRegistry()
        reg.register_toolkit(_GoodToolkit())
        assert sorted(reg.list()) == ["calc:add", "calc:subtract"]


class TestToolRegistrySchemas:
    def test_schemas_flat_list(self):
        reg = ToolRegistry()
        reg.register_toolkit(_GoodToolkit())
        schemas = reg.schemas()
        assert len(schemas) == 2
        names = {s["name"] for s in schemas}
        assert names == {"calc:add", "calc:subtract"}

    def test_schemas_by_toolkit_grouped(self):
        reg = ToolRegistry()
        reg.register_toolkit(_GoodToolkit())
        grouped = reg.schemas_by_toolkit()
        assert "calc" in grouped
        assert "add" in grouped["calc"]
        assert "subtract" in grouped["calc"]


class TestToolRegistryDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_success(self):
        reg = ToolRegistry()
        reg.register_toolkit(_GoodToolkit())
        result = await reg.dispatch("calc:add", {"a": 3, "b": 4})
        assert result.ok is True
        assert result.data == 7

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self):
        reg = ToolRegistry()
        with pytest.raises(UnknownToolError):
            await reg.dispatch("no:such", {})

    @pytest.mark.asyncio
    async def test_dispatch_validation_error(self):
        reg = ToolRegistry()
        reg.register_toolkit(_GoodToolkit())
        with pytest.raises(ToolValidationError) as exc_info:
            await reg.dispatch("calc:add", {"a": "not_int", "b": 1})
        assert exc_info.value.qualified_name == "calc:add"

    @pytest.mark.asyncio
    async def test_dispatch_tool_exception_returns_failure(self):
        class _FailToolkit:
            namespace = "fail"

            def boom(self, msg: str) -> str:
                """Raise."""
                raise RuntimeError(msg)

        reg = ToolRegistry()
        reg.register_toolkit(_FailToolkit())
        result = await reg.dispatch("fail:boom", {"msg": "kaboom"})
        assert result.ok is False
        assert "kaboom" in result.error

    @pytest.mark.asyncio
    async def test_dispatch_validates_before_calling(self):
        call_tracker = []

        class _Tracker:
            namespace = "track"

            def log(self, msg: str) -> None:
                """Log."""
                call_tracker.append(msg)

        reg = ToolRegistry()
        reg.register_toolkit(_Tracker())
        await reg.dispatch("track:log", {"msg": "hello"})
        assert call_tracker == ["hello"]

    @pytest.mark.asyncio
    async def test_dispatch_missing_required_field_causes_validation_error(self):
        reg = ToolRegistry()
        reg.register_toolkit(_GoodToolkit())
        with pytest.raises(ToolValidationError):
            await reg.dispatch("calc:add", {})


# ─────────────────────────────────────────────
# Toolkit base class
# ─────────────────────────────────────────────


class TestToolkit:
    def test_has_namespace(self):
        t = Toolkit()
        t.namespace = "test"
        assert t.namespace == "test"
