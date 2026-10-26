"""Claude 5.x request settings: thinking and effort resolution, strict-tool and structured-output schemas."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from skazki_bot.config import Settings, resolve_thinking
from skazki_bot.harness.guard import parse_critic
from skazki_bot.harness.prompts import CRITIC_CODES, CRITIC_SCHEMA, CRITIC_SYSTEM
from skazki_bot.harness.tools import TOOL_SPECS
from skazki_bot.llm import build_llm
from skazki_bot.llm.anthropic_llm import AnthropicLLM


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"bot_token": "1:T", "anthropic_api_key": "sk-test"} | overrides
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("model", "mode", "expected"),
    [
        ("claude-sonnet-5-5", "auto", "between_tools"),
        ("claude-haiku-5-5", "auto", "adaptive"),
        ("claude-opus-5-5", "auto", "adaptive"),
        ("claude-sonnet-5-5", "adaptive", "adaptive"),
        ("claude-sonnet-5-5", "between_tools", "between_tools"),
    ],
)
def test_resolve_thinking(model: str, mode: Any, expected: str) -> None:
    assert resolve_thinking(model, mode) == expected


def test_defaults_are_latency_friendly() -> None:
    cfg = settings()
    assert (cfg.llm_effort, cfg.llm_thinking, cfg.guard_effort) == ("medium", "auto", "low")
    assert cfg.llm_strict_tools is True


def test_between_tools_cannot_run_at_xhigh_or_max() -> None:
    with pytest.raises(ValidationError, match="between_tools"):
        settings(llm_effort="max")  # the default model resolves to between_tools
    assert settings(llm_effort="max", llm_thinking="adaptive").llm_effort == "max"
    assert settings(llm_effort="xhigh", llm_model="claude-opus-5-5").llm_effort == "xhigh"


def test_build_llm_passes_the_request_settings_through() -> None:
    llm = build_llm(settings(llm_effort="low", guard_effort="medium", llm_strict_tools=False))
    assert isinstance(llm, AnthropicLLM)
    assert (llm._effort, llm._guard_effort) == ("low", "medium")
    assert llm._thinking == "between_tools"
    assert llm._strict_tools is False


# --- strict tool use and structured outputs accept only a subset of JSON Schema -----------------------
ALLOWED_KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "description",
    "enum",
    "items",
}


def violations(schema: dict[str, Any], path: str = "$") -> list[str]:
    found = [f"{path}: unsupported key {k!r}" for k in schema if k not in ALLOWED_KEYS]
    if schema.get("type") == "object":
        if schema.get("additionalProperties") is not False:
            found.append(f"{path}: object must set additionalProperties: false")
        for name, sub in schema.get("properties", {}).items():
            found += violations(sub, f"{path}.{name}")
    if isinstance(schema.get("items"), dict):
        found += violations(schema["items"], f"{path}[]")
    return found


def optional_count(schema: dict[str, Any]) -> int:
    own = 0
    if schema.get("type") == "object":
        props = schema.get("properties", {})
        own = len(set(props) - set(schema.get("required", [])))
        own += sum(optional_count(sub) for sub in props.values())
    if isinstance(schema.get("items"), dict):
        own += optional_count(schema["items"])
    return own


def test_strict_tool_schemas_stay_in_the_supported_subset() -> None:
    strict = [t for t in TOOL_SPECS.values() if t.strict]
    assert strict, "the skill tools should use strict tool use"
    for spec in strict:
        assert violations(spec.input_schema) == [], spec.name
    assert len(strict) <= 20  # API limit on strict tools per request


def test_optional_parameters_stay_under_the_api_limit() -> None:
    total = sum(optional_count(t.input_schema) for t in TOOL_SPECS.values() if t.strict)
    assert total + optional_count(CRITIC_SCHEMA) <= 24  # one request can carry both kinds


def test_critic_schema_is_in_the_supported_subset_and_matches_the_prompt() -> None:
    assert violations(CRITIC_SCHEMA) == []
    item = CRITIC_SCHEMA["properties"]["issues"]["items"]
    assert item["properties"]["code"]["enum"] == list(CRITIC_CODES)
    for code in CRITIC_CODES:
        assert code in CRITIC_SYSTEM  # the prompt names every code the schema allows
    assert set(item["required"]) == set(item["properties"])  # nothing optional


def test_parse_critic_tolerates_enum_capitalisation() -> None:
    raw = '{"ok": false, "issues": [{"code": "Safety", "severity": "Block", "message": "Страшно"}]}'
    (issue,) = parse_critic(raw)
    assert (issue.code, issue.severity) == ("critic_safety", "block")
