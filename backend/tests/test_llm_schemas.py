"""Phase 3 — LLM schema + heuristic-fallback tests (no Ollama required)."""

from app.llm.nl_mission_parser import heuristic_parse
from app.llm.psi_synthesis import heuristic_psi
from app.llm.schemas import NLParseResult, PsiSynthesis, ollama_format_schema


def test_psi_schema_inlines_refs():
    schema = ollama_format_schema(PsiSynthesis)
    # No unresolved $ref / $defs left for Ollama's format field.
    dumped = str(schema)
    assert "$ref" not in dumped and "$defs" not in dumped
    assert schema["properties"]["kappa"]["enum"]  # kappa is enum-constrained


def test_nlparse_schema_valid():
    schema = ollama_format_schema(NLParseResult)
    assert "actions" in schema["properties"]


def test_heuristic_psi_pharma_cold_chain():
    r = heuristic_psi("Urgent insulin delivery, maintain 2-8C cold chain")
    assert r["kappa"] == "PHARMA"
    assert (r["temp_min"], r["temp_max"]) == (2.0, 8.0)
    assert r["priority"] == 3.0  # 'urgent' -> life-critical
    # Validates against the strict schema.
    PsiSynthesis(**{k: v for k, v in r.items() if k in PsiSynthesis.model_fields})


def test_heuristic_parse_emergency():
    r = heuristic_parse("abort mission and return to depot immediately", ["SDM Hospital"])
    assert r["actions"][0]["type"] == "EMERGENCY_RETURN"
    NLParseResult(**{k: v for k, v in r.items() if k in NLParseResult.model_fields})


def test_heuristic_parse_split_delivery():
    r = heuristic_parse("split the insulin delivery, ground agent takes final leg", ["Hospital B"])
    assert r["actions"][0]["type"] == "SPLIT_DELIVERY"
