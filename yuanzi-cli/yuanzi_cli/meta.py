"""Pydantic model for validating atom meta.yaml files."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class RuntimeConfig(BaseModel):
    """Runtime configuration for an atom."""

    interface: Literal["std-atom-http-v1"] = "std-atom-http-v1"
    port: int = Field(..., ge=1, le=65535)
    host: str = "127.0.0.1"
    state: Literal["stateless", "stateful"] = "stateless"
    execution: Literal["sync", "async"] = "sync"


class AtomMeta(BaseModel):
    """Validated representation of an atom meta.yaml file."""

    id: str = Field(..., description="Reverse-domain atom identifier")
    version: str = Field(..., description="Semantic version")
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    type: Literal["skill", "data", "env", "agent"]
    kernel_type: Literal["python_script", "markdown_rules", "prompt_txt"]
    author: str = Field(..., min_length=1)
    license: str = Field(..., min_length=1)
    dependencies: list[str] = []
    tags: list[str] = []
    runtime: RuntimeConfig

    @field_validator("id")
    @classmethod
    def validate_atom_id(cls, value: str) -> str:
        if not value:
            raise ValueError("atom id must not be empty")
        parts = value.split(".")
        if len(parts) < 2:
            raise ValueError(
                "atom id must use reverse-domain notation (e.g. com.example.my-atom)"
            )
        for part in parts:
            if not part:
                raise ValueError("atom id segments must not be empty")
            if not all(c.isalnum() or c in "-_" for c in part):
                raise ValueError(
                    f"atom id segment '{part}' contains invalid characters"
                )
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        # Loose semantic-version check: major.minor.patch with optional prerelease/build.
        parts = value.split("+", 1)[0].split("-", 1)[0].split(".")
        if len(parts) < 2:
            raise ValueError("version must have at least major.minor (e.g. 0.1.0)")
        for part in parts:
            if not part.isdigit():
                raise ValueError(f"version component '{part}' must be numeric")
        return value

    @model_validator(mode="after")
    def check_dependencies(self) -> "AtomMeta":
        for dep in self.dependencies:
            if not dep:
                raise ValueError("dependency atom id must not be empty")
        return self


def load_meta(path: str) -> dict[str, Any]:
    """Load a meta.yaml file and return the raw dictionary."""
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def validate_meta(data: dict[str, Any]) -> AtomMeta:
    """Validate raw meta.yaml data and return a typed model."""
    return AtomMeta.model_validate(data)
