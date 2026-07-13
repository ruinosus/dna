"""Solution A — Pydantic models for a YAML-folder agent stack.

This is the validation layer the founder's critique names: "a folder of plain
YAML + Pydantic models for validation". Every kind (Soul, Skill, Guardrail,
Agent) is a Pydantic model; `load_*` reads the YAML and validates it, raising a
readable error on a schema mistake.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Soul(BaseModel):
    name: str
    body: str


class Skill(BaseModel):
    name: str
    description: str
    body: str


class Guardrail(BaseModel):
    name: str
    description: str
    severity: Literal["info", "warning", "error"] = "error"
    scope: Literal["input", "output", "both"] = "output"
    rules: list[str] = Field(min_length=1)


class Agent(BaseModel):
    name: str
    description: str = ""
    instruction: str
    layout: Literal["persona-first", "instruction-first"] = "instruction-first"
    soul: str | None = None
    skills: list[str] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)
    model: str

    @field_validator("model")
    @classmethod
    def _model_has_provider(cls, v: str) -> str:
        if "/" not in v:
            raise ValueError(
                f"model {v!r} must be a 'provider/name' coordinate, e.g. 'azure/gpt-4o'"
            )
        return v
