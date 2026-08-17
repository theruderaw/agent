"""
base.py

Core abstractions for the tool layer.

Design:
- A "toolkit" is a plain class whose public methods are tools
  (e.g. FilesystemTools.read_path, FilesystemTools.write_path).
- Tool schemas are NOT hand-written. They are derived automatically
  from each method's type-hinted signature + docstring.
- Registry keys are namespaced as "module:tool_name", e.g. "filesystem:read_path".
- Dispatch is generic: registry.dispatch(qualified_name, raw_args) validates
  raw_args against a Pydantic model built from the method signature, then
  calls the bound method. No per-tool parsing code anywhere.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, get_type_hints

from pydantic import BaseModel, ValidationError, create_model


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class ToolError(Exception):
    """Base class for tool-layer errors."""


class UnknownToolError(ToolError):
    def __init__(self, qualified_name: str):
        super().__init__(f"No tool registered under '{qualified_name}'")
        self.qualified_name = qualified_name


class ToolRegistrationError(ToolError):
    """Raised when a toolkit or method can't be registered (bad shape)."""


class ToolValidationError(ToolError):
    """Raised when raw arguments fail validation against a tool's schema."""
    def __init__(self, qualified_name: str, errors: ValidationError):
        super().__init__(f"Invalid arguments for '{qualified_name}': {errors}")
        self.qualified_name = qualified_name
        self.errors = errors


# --------------------------------------------------------------------------
# Result envelope
# --------------------------------------------------------------------------

@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None

    @classmethod
    def success(cls, data: Any) -> "ToolResult":
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, error: str) -> "ToolResult":
        return cls(ok=False, error=error)


# --------------------------------------------------------------------------
# Toolkit convention (no ABC — just a required attribute)
# --------------------------------------------------------------------------

class Toolkit:
    """
    Optional convenience base. A toolkit only needs a `namespace` attribute
    and public, type-hinted, docstringed methods. Inheriting from this class
    is not required — register_toolkit() only checks for `namespace` via
    getattr, so any plain class with that attribute works too.
    """
    namespace: str


# --------------------------------------------------------------------------
# Tool record (built by introspection, not written by hand)
# --------------------------------------------------------------------------

@dataclass
class Tool:
    namespace: str
    method_name: str
    description: str
    args_model: type[BaseModel]
    bound_method: Callable[..., Any]
    skills: str | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.namespace}:{self.method_name}"

    def schema(self) -> dict:
        schema = {
            "name": self.qualified_name,
            "description": self.description,
            "input_schema": self.args_model.model_json_schema(),
        }
        if self.skills is not None:
            schema["skills"] = self.skills
        return schema


# --------------------------------------------------------------------------
# Introspection: method signature -> Pydantic args model
# --------------------------------------------------------------------------

def _build_args_model(namespace: str, method_name: str, method: Callable) -> type[BaseModel]:
    sig = inspect.signature(method)
    hints = get_type_hints(method)

    fields: dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue  # *args / **kwargs not supported in schema generation

        if param_name not in hints:
            raise ToolRegistrationError(
                f"'{namespace}.{method_name}' parameter '{param_name}' is missing a type hint"
            )

        annotation = hints[param_name]
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[param_name] = (annotation, default)

    model_name = f"{namespace.title()}{method_name.title().replace('_', '')}Args"
    return create_model(model_name, **fields)  # type: ignore[call-overload]


def _extract_description(method: Callable) -> str:
    doc = inspect.getdoc(method)
    if not doc:
        raise ToolRegistrationError(
            f"'{method.__qualname__}' is missing a docstring (used as the tool description)"
        )
    # Use the summary line only; keep it simple for v1.
    return doc.strip().splitlines()[0].strip()


def _public_methods(instance: object):
    for attr_name in dir(instance):
        if attr_name.startswith("_"):
            continue
        attr = getattr(instance, attr_name)
        if callable(attr) and inspect.ismethod(attr):
            yield attr_name, attr


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register_toolkit(self, instance: object) -> None:
        namespace = getattr(instance, "namespace", None)
        skills = getattr(instance, "skills", None)
        if not namespace:
            raise ToolRegistrationError(
                f"{type(instance).__name__} must define a 'namespace' attribute"
            )

        for method_name, bound_method in _public_methods(instance):
            qualified_name = f"{namespace}:{method_name}"
            if qualified_name in self._tools:
                raise ToolRegistrationError(f"Duplicate tool registration: '{qualified_name}'")

            args_model = _build_args_model(namespace, method_name, bound_method)
            description = _extract_description(bound_method)

            self._tools[qualified_name] = Tool(
                namespace=namespace,
                method_name=method_name,
                description=description,
                args_model=args_model,
                bound_method=bound_method,
                skills=skills,
            )

    def get(self, qualified_name: str) -> Tool:
        try:
            return self._tools[qualified_name]
        except KeyError:
            raise UnknownToolError(qualified_name) from None

    def list(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self._tools.values()]

    def schemas_by_toolkit(self) -> dict[str, dict[str, dict]]:
        """Same schemas as schemas(), grouped under namespace, keyed by tool name within each."""
        grouped: dict[str, dict[str, dict]] = {}
        for tool in self._tools.values():
            grouped.setdefault(tool.namespace, {})[tool.method_name] = tool.schema()
        return grouped

    def dispatch(self, qualified_name: str, raw_arguments: dict) -> ToolResult:
        """
        LLM -> qualified_name + raw_arguments -> registry -> tool
        -> Pydantic validation -> execute -> ToolResult
        """
        tool = self.get(qualified_name)

        try:
            validated = tool.args_model(**raw_arguments)
        except ValidationError as e:
            raise ToolValidationError(qualified_name, e) from e

        try:
            result = tool.bound_method(**validated.model_dump())
        except Exception as e:  # noqa: BLE001 - tool failures shouldn't crash the runtime
            return ToolResult.failure(str(e))

        return ToolResult.success(result)