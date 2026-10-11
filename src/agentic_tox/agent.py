"""The agent loop.

Two planners, one set of tools and one output format:

* `plan_deterministic` is the default and needs no API key. It reads the
  question for a CAS number and a hazard intent, then calls the tools in a
  fixed order. It is what the tests exercise and what the live demo runs.
* `plan_llm` hands the same tools to Claude or an OpenAI model and lets it
  choose. It is opt-in through `AGENTIC_TOX_LLM` and is a strict superset of
  nothing: if it fails, the deterministic path is still there.

The point of having both is the comparison. The deterministic planner shows
that most of the value is in the tools and the provenance discipline, not in
the model doing the planning.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from . import kg, model
from .provenance import Fact, now

POSITIVE_TOKENS = ("positive",)
NEGATIVE_TOKENS = ("negative",)
EQUIVOCAL_TOKENS = ("equivocal", "inconclusive")
DECISION_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def tool_resolve_chemical(cas: str) -> list[Fact]:
    """Resolve a CAS number to a structure (SMILES) and PubChem CID."""
    _, facts = kg.resolve_chemical(cas)
    return facts


def tool_library_membership(cas: str) -> list[Fact]:
    """Report whether the chemical is in the Tox21 10K screening library."""
    return kg.tox21_identity(cas)


def tool_measured_genotoxicity(cas: str) -> list[Fact]:
    """Measured in vitro and in vivo genotoxicity records from the ICE brick."""
    return kg.genotoxicity_evidence(cas)


def tool_carcinogenicity(cas: str) -> list[Fact]:
    """Authoritative carcinogenicity classifications (IARC, NTP, IRIS, RoC)."""
    return kg.carcinogenicity_evidence(cas)


def tool_predict_mutagenicity(smiles: str) -> list[Fact]:
    """Run ToxTransformer on the three bacterial-mutagenicity style endpoints."""
    return model.predict_panel(smiles, model.MUTAGENICITY_ENDPOINTS, progress=_progress)


def tool_predict_dna_damage(smiles: str) -> list[Fact]:
    """Run ToxTransformer on the Tox21 DNA-damage and p53 endpoints."""
    return model.predict_panel(smiles, model.DNA_DAMAGE_ENDPOINTS, progress=_progress)


TOOLS = {
    "resolve_chemical": (tool_resolve_chemical, "cas"),
    "library_membership": (tool_library_membership, "cas"),
    "measured_genotoxicity": (tool_measured_genotoxicity, "cas"),
    "carcinogenicity": (tool_carcinogenicity, "cas"),
    "predict_mutagenicity": (tool_predict_mutagenicity, "smiles"),
    "predict_dna_damage": (tool_predict_dna_damage, "smiles"),
}


def _progress(message: str) -> None:
    print(message, flush=True)


# ---------------------------------------------------------------------------
# Trace and answer
# ---------------------------------------------------------------------------


@dataclass
class Step:
    tool: str
    argument: str
    facts: list[Fact]
    why: str = ""


@dataclass
class Answer:
    question: str
    verdict: str
    reasoning: list[str]
    steps: list[Step] = field(default_factory=list)
    planner: str = "deterministic"
    started_at: str = field(default_factory=now)

    @property
    def facts(self) -> list[Fact]:
        return [fact for step in self.steps for fact in step.facts]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "planner": self.planner,
            "started_at": self.started_at,
            "verdict": self.verdict,
            "reasoning": self.reasoning,
            "steps": [
                {
                    "tool": step.tool,
                    "argument": step.argument,
                    "why": step.why,
                    "facts": [fact.to_dict() for fact in step.facts],
                }
                for step in self.steps
            ],
        }

    def render(self) -> str:
        out = [
            "=" * 78,
            f"QUESTION  {self.question}",
            f"PLANNER   {self.planner} (no API key required)"
            if self.planner == "deterministic"
            else f"PLANNER   {self.planner}",
            "=" * 78,
            "",
        ]
        for number, step in enumerate(self.steps, 1):
            out.append(f"[{number}] {step.tool}({step.argument})")
            if step.why:
                out.append(f"    why: {step.why}")
            if not step.facts:
                out.append("  (no records)")
            for fact in step.facts:
                out.extend(fact.lines())
            out.append("")
        out.append("-" * 78)
        out.append("ANSWER")
        out.append("-" * 78)
        out.append(self.verdict)
        out.append("")
        for line in self.reasoning:
            out.append(f"  * {line}")
        out.append("")
        out.append(
            "Every line above is traceable: dataset digest, model weights hash, or API\n"
            "request, with the time it was read. This is a demonstration of tool wiring\n"
            "and provenance, not a regulatory conclusion or a hazard assessment."
        )
        return "\n".join(out)


# ---------------------------------------------------------------------------
# Deterministic planner
# ---------------------------------------------------------------------------

CAS_RE = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")

NAME_TO_CAS = {
    "oxybenzone": "131-57-7",
    "2-hydroxy-4-methoxybenzophenone": "131-57-7",
    "bisphenol a": "80-05-7",
    "acetaminophen": "103-90-2",
    "paracetamol": "103-90-2",
}


def parse_question(question: str) -> dict:
    """Pull the chemical and the intent out of a plain-language question."""
    lowered = question.lower()
    cas = None
    found = CAS_RE.search(question)
    if found:
        cas = found.group(1)
    else:
        for name, value in NAME_TO_CAS.items():
            if name in lowered:
                cas = value
                break
    intents = set()
    if any(word in lowered for word in ("mutagen", "ames", "genotox", "dna damage")):
        intents.add("mutagenicity")
    if any(word in lowered for word in ("cancer", "carcinogen", "tumour", "tumor")):
        intents.add("carcinogenicity")
    if not intents:
        intents.add("mutagenicity")
    return {"cas": cas, "intents": sorted(intents)}


def _responses(facts: list[Fact]) -> dict:
    """Count call types across measured records, splitting multi-study strings."""
    counts = {"positive": 0, "negative": 0, "equivocal": 0}
    for fact in facts:
        for call in str(fact.value).split(";"):
            call = call.strip().lower()
            if not call:
                continue
            if any(token in call for token in EQUIVOCAL_TOKENS):
                counts["equivocal"] += 1
            elif any(token in call for token in POSITIVE_TOKENS):
                counts["positive"] += 1
            elif any(token in call for token in NEGATIVE_TOKENS):
                counts["negative"] += 1
    return counts


def plan_deterministic(question: str) -> Answer:
    parsed = parse_question(question)
    cas = parsed["cas"]
    if not cas:
        raise SystemExit(
            "No CAS number found in the question. Include one, for example "
            "'Is oxybenzone (CAS 131-57-7) likely mutagenic?'"
        )
    steps: list[Step] = []

    identity_facts = tool_resolve_chemical(cas)
    steps.append(
        Step("resolve_chemical", cas, identity_facts, "the model predicts on a structure, so fix the structure first")
    )
    smiles = identity_facts[0].value["smiles"]
    name = identity_facts[0].value["name"]

    steps.append(
        Step("library_membership", cas, tool_library_membership(cas), "has this chemical actually been screened?")
    )

    measured = tool_measured_genotoxicity(cas)
    steps.append(Step("measured_genotoxicity", cas, measured, "measured data outranks any prediction"))

    bacterial = [f for f in measured if "Bacterial mutagenicity" in f.statement]
    in_vivo = [f for f in measured if "Micronucleus" in f.statement or "Comet" in f.statement]

    if "carcinogenicity" in parsed["intents"]:
        steps.append(
            Step("carcinogenicity", cas, tool_carcinogenicity(cas), "the question asked about cancer as well")
        )

    predicted = tool_predict_mutagenicity(smiles)
    steps.append(
        Step(
            "predict_mutagenicity",
            smiles,
            predicted,
            "fill the gap the measured record leaves, and check the model against what is measured",
        )
    )
    dna = tool_predict_dna_damage(smiles)
    steps.append(Step("predict_dna_damage", smiles, dna, "a second, mechanistically different model endpoint"))

    counts = _responses(bacterial)
    probabilities = [fact.value for fact in predicted]
    mean_probability = sum(probabilities) / len(probabilities)
    model_call = "active" if mean_probability >= DECISION_THRESHOLD else "not active"

    reasoning = []
    if bacterial:
        reasoning.append(
            f"Measured bacterial mutagenicity in ICE: {counts['positive']} positive, "
            f"{counts['negative']} negative, {counts['equivocal']} equivocal study calls "
            f"across {len(bacterial)} record(s)."
        )
    else:
        reasoning.append("ICE holds no bacterial mutagenicity record for this CAS, so the model is filling a real gap.")
    if in_vivo:
        reasoning.append(
            "In vivo genotoxicity records present: "
            + "; ".join(f"{f.source.detail['endpoint']} {f.value}" for f in in_vivo)
            + "."
        )
    reasoning.append(
        f"ToxTransformer mean p(active) across {len(predicted)} mutagenicity-style endpoints = "
        f"{mean_probability:.3f}, which at a 0.5 cut reads as {model_call}. Per-endpoint: "
        + ", ".join(f"{f.source.detail['property_title'][:42]} {f.value:.3f}" for f in predicted)
        + "."
    )
    reasoning.append(
        "DNA-damage endpoints: "
        + ", ".join(f"{f.source.detail['property_title'][:42]} {f.value:.3f}" for f in dna)
        + "."
    )

    measured_positive = counts["positive"] > counts["negative"]
    if bacterial and measured_positive == (mean_probability >= DECISION_THRESHOLD):
        agreement = "The measured record and the model agree."
    elif bacterial:
        agreement = (
            "The measured record and the model disagree, which is the interesting case: "
            "the measured calls are what you would cite, and the disagreement is what you "
            "would investigate."
        )
    else:
        agreement = "There is no measured call here to compare the model against."

    if bacterial and not measured_positive and counts["positive"] == 0:
        verdict = (
            f"{name} (CAS {cas}): the public measured record in ICE is negative for bacterial "
            f"mutagenicity, and ToxTransformer also predicts not active (mean p = {mean_probability:.3f}). "
            "On this evidence it is not likely to be a bacterial mutagen."
        )
    elif bacterial and not measured_positive and counts["positive"] > 0:
        verdict = (
            f"{name} (CAS {cas}): the public measured record in ICE is mixed and mostly negative "
            f"({counts['positive']} positive / {counts['negative']} negative study calls), and "
            f"ToxTransformer predicts {model_call} (mean p = {mean_probability:.3f}). The weight of "
            "the public evidence does not support a mutagenicity call, but it is not clean."
        )
    elif bacterial:
        verdict = (
            f"{name} (CAS {cas}): the public measured record in ICE is predominantly positive for "
            f"bacterial mutagenicity ({counts['positive']} positive / {counts['negative']} negative "
            f"study calls), and ToxTransformer predicts {model_call} (mean p = {mean_probability:.3f})."
        )
    else:
        verdict = (
            f"{name} (CAS {cas}): no measured bacterial mutagenicity record in this ICE slice. "
            f"ToxTransformer alone predicts {model_call} (mean p = {mean_probability:.3f}), which is a "
            "prediction and not evidence."
        )
    reasoning.append(agreement)
    reasoning.append(
        "Limits: the model's endpoints are assay-level binary labels, not an OECD 471 call; "
        "the ICE slice is two tables, not the whole brick; neither covers metabolism, "
        "exposure or dose."
    )
    return Answer(question=question, verdict=verdict, reasoning=reasoning, steps=steps)


# ---------------------------------------------------------------------------
# Optional LLM planner
# ---------------------------------------------------------------------------

LLM_TOOL_SCHEMAS = [
    {
        "name": "resolve_chemical",
        "description": tool_resolve_chemical.__doc__,
        "parameter": "cas",
    },
    {
        "name": "library_membership",
        "description": tool_library_membership.__doc__,
        "parameter": "cas",
    },
    {
        "name": "measured_genotoxicity",
        "description": tool_measured_genotoxicity.__doc__,
        "parameter": "cas",
    },
    {"name": "carcinogenicity", "description": tool_carcinogenicity.__doc__, "parameter": "cas"},
    {
        "name": "predict_mutagenicity",
        "description": tool_predict_mutagenicity.__doc__,
        "parameter": "smiles",
    },
    {
        "name": "predict_dna_damage",
        "description": tool_predict_dna_damage.__doc__,
        "parameter": "smiles",
    },
]

SYSTEM_PROMPT = """You are a toxicology research assistant with three kinds of tool:
chemical identity, measured public data, and a predictive model. Rules:
1. Resolve the chemical to a structure before predicting anything.
2. Prefer measured data. State a prediction as a prediction.
3. Never state a fact a tool did not return. Cite the tool for each claim.
4. Finish with a short verdict and a list of its limits.
Answer in plain text. Use the tools; do not answer from memory."""

MAX_TURNS = 8


def _llm_tools_anthropic():
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": {
                "type": "object",
                "properties": {tool["parameter"]: {"type": "string"}},
                "required": [tool["parameter"]],
            },
        }
        for tool in LLM_TOOL_SCHEMAS
    ]


def _run_tool(name: str, arguments: dict) -> tuple[list[Fact], str]:
    function, parameter = TOOLS[name]
    argument = arguments.get(parameter, "")
    facts = function(argument)
    return facts, argument


def plan_llm(question: str, provider: str) -> Answer:
    """Let a model choose the tools. Opt-in, and not the tested default."""
    steps: list[Step] = []
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic()
        name = os.environ.get("AGENTIC_TOX_MODEL", "claude-sonnet-5-5")
        messages = [{"role": "user", "content": question}]
        final_text = ""
        for _ in range(MAX_TURNS):
            response = client.messages.create(
                model=name,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                tools=_llm_tools_anthropic(),
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "text":
                    final_text = block.text
                elif block.type == "tool_use":
                    facts, argument = _run_tool(block.name, dict(block.input))
                    steps.append(Step(block.name, argument, facts, "chosen by the model"))
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps([fact.to_dict() for fact in facts])[:20000],
                        }
                    )
            if not results:
                break
            messages.append({"role": "user", "content": results})
        verdict = final_text or "The model returned no final text."
        return Answer(question, verdict, ["Planned by the model, not by the rule-based planner."], steps, f"anthropic:{name}")

    if provider == "openai":
        from openai import OpenAI

        client = OpenAI()
        name = os.environ.get("AGENTIC_TOX_MODEL", "gpt-4.1")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {tool["parameter"]: {"type": "string"}},
                        "required": [tool["parameter"]],
                    },
                },
            }
            for tool in LLM_TOOL_SCHEMAS
        ]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        final_text = ""
        for _ in range(MAX_TURNS):
            response = client.chat.completions.create(model=name, messages=messages, tools=tools)
            message = response.choices[0].message
            messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                final_text = message.content or ""
                break
            for call in message.tool_calls:
                facts, argument = _run_tool(call.function.name, json.loads(call.function.arguments))
                steps.append(Step(call.function.name, argument, facts, "chosen by the model"))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps([fact.to_dict() for fact in facts])[:20000],
                    }
                )
        verdict = final_text or "The model returned no final text."
        return Answer(question, verdict, ["Planned by the model, not by the rule-based planner."], steps, f"openai:{name}")

    raise SystemExit(f"Unknown AGENTIC_TOX_LLM provider: {provider}. Use 'anthropic' or 'openai'.")


def answer(question: str, planner: str | None = None) -> Answer:
    """Answer a hazard question. Deterministic unless an LLM is requested."""
    provider = planner or os.environ.get("AGENTIC_TOX_LLM", "")
    if provider and provider not in ("none", "deterministic"):
        return plan_llm(question, provider)
    return plan_deterministic(question)
