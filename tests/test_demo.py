"""Tests for the no-key path. These need network access on first run.

They are deliberately cheap and mostly about the claims docs/local-demo.md makes:
the pins match the published catalog, every fact carries provenance, and the
recorded prediction for the demo chemical still reproduces on CPU.
"""

import json

import pytest

from agentic_tox import agent, kg, model


def test_question_parsing():
    parsed = agent.parse_question("Is oxybenzone (CAS 131-57-7) likely mutagenic?")
    assert parsed["cas"] == "131-57-7"
    assert "mutagenicity" in parsed["intents"]
    assert agent.parse_question("Is bisphenol A carcinogenic?")["cas"] == "80-05-7"


def test_endpoint_pins_match_catalog():
    """A catalog change upstream must fail loudly, not shift the endpoint."""
    directory = model.fetch_weights(progress=lambda _m: None)
    catalog = json.loads((directory / "properties.json").read_text())
    for endpoint in model.ENDPOINTS.values():
        entry = catalog[endpoint.index]
        assert entry["property_id"] == endpoint.property_id
        assert entry["title"] == endpoint.title
        assert entry["source"] == endpoint.catalog_source


def test_ice_slice_loads_and_is_verified():
    frame, source = kg.load_table("Cancer")
    assert len(frame) > 10_000
    assert source.digest == kg.TABLES["Cancer"]["md5"]
    assert "131-57-7" in set(frame["CASRN"])


def test_oxybenzone_prediction_reproduces():
    fact = model.predict(
        "COC1=CC(=C(C=C1)C(=O)C2=CC=CC=C2)O",
        "bacterial_mutagenicity",
        progress=lambda _m: None,
    )
    assert fact.value == pytest.approx(0.2104, abs=2e-3)
    assert fact.source.digest == model.ARTIFACTS[0]["sha256"]


def test_deterministic_answer_is_fully_sourced():
    result = agent.answer(
        "Is oxybenzone (CAS 131-57-7) likely mutagenic, and what does the evidence say?",
        planner="deterministic",
    )
    assert result.planner == "deterministic"
    assert len(result.steps) >= 5
    assert result.facts, "an answer with no facts is a bug"
    for fact in result.facts:
        assert fact.source.name and fact.source.url and fact.source.retrieved_at
        assert fact.source.kind in ("dataset", "api", "model")
    assert "131-57-7" in result.verdict
    rendered = result.render()
    assert "provenance:" in rendered
    assert "not a regulatory conclusion" in rendered


def test_missing_cas_is_refused():
    with pytest.raises(SystemExit):
        agent.answer("Is this stuff dangerous?", planner="deterministic")
