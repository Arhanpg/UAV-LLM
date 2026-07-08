"""Tests for via/waypoint parsing, kappa sanitization and quantity extraction."""

import pytest
from app.llm.nl_mission_parser import (
    _extract_quantity,
    _infer_kappa_from_text,
    _sanitize_kappa,
    heuristic_parse,
)

LOCS = [
    "SDM Hospital & Medical College",
    "KIMS Hospital Dharwad",
    "Sana Shaheen Independent PU College",
    "Dharwad Railway Station",
    "Karnataka University",
    "KMF Hubli",
    "Nandini Dairy Hubli",
]


class TestSanitizeKappa:
    def test_valid_classes_pass_through(self):
        for cls in ("PHARMA", "FOOD", "ELECTRONICS", "FLAMMABLE", "OXIDIZER", "CRYOGENIC", "GENERAL"):
            assert _sanitize_kappa(cls) == cls

    def test_notebook_maps_to_general(self):
        assert _sanitize_kappa("3 notebooks") == "GENERAL"

    def test_milk_maps_to_food(self):
        assert _sanitize_kappa("2 L milk") == "FOOD"
        assert _sanitize_kappa("MILK") == "FOOD"

    def test_insulin_maps_to_pharma(self):
        assert _sanitize_kappa("insulin vials") == "PHARMA"

    def test_none_maps_to_general(self):
        assert _sanitize_kappa(None) == "GENERAL"
        assert _sanitize_kappa("") == "GENERAL"

    def test_unknown_maps_to_general(self):
        assert _sanitize_kappa("random stuff xyz") == "GENERAL"


class TestInferKappa:
    def test_milk(self):
        assert _infer_kappa_from_text("pick up 2L milk") == "FOOD"

    def test_kmf_nandini(self):
        assert _infer_kappa_from_text("collect from KMF") == "FOOD"
        assert _infer_kappa_from_text("nandini dairy") == "FOOD"

    def test_insulin(self):
        assert _infer_kappa_from_text("deliver insulin to hospital") == "PHARMA"

    def test_notebooks(self):
        assert _infer_kappa_from_text("give them 3 notebooks") == "GENERAL"


class TestExtractQuantity:
    def test_litres(self):
        qty, kg = _extract_quantity("2 L milk")
        assert qty == 2
        assert kg == pytest.approx(2.0)

    def test_ml(self):
        _, kg = _extract_quantity("500 ml water")
        assert kg == pytest.approx(0.5)

    def test_notebooks(self):
        qty, kg = _extract_quantity("3 notebooks")
        assert qty == 3
        assert kg == pytest.approx(0.9)

    def test_no_unit(self):
        qty, kg = _extract_quantity("deliver 5 packages")
        assert qty == 5


class TestViaWaypoint:
    def test_go_through_emits_add_stop(self):
        result = heuristic_parse(
            "So go through Sana Shaheen Independent PU College and give them 3 notebooks",
            LOCS,
        )
        types = [a["type"] for a in result["actions"]]
        assert "ADD_STOP" in types
        stop = next(a for a in result["actions"] if a["type"] == "ADD_STOP")
        assert stop["location"] == "Sana Shaheen Independent PU College"

    def test_deliver_also_emitted(self):
        result = heuristic_parse(
            "So go through Sana Shaheen Independent PU College and give them 3 notebooks",
            LOCS,
        )
        types = [a["type"] for a in result["actions"]]
        assert "DELIVER" in types

    def test_kappa_valid(self):
        from app.config import CLASSES
        result = heuristic_parse(
            "So go through Sana Shaheen Independent PU College and give them 3 notebooks",
            LOCS,
        )
        for act in result["actions"]:
            assert act["package_kappa"] in CLASSES


class TestKMFMilk:
    def test_kmf_pickup_parsed(self):
        result = heuristic_parse(
            "Go to KMF Hubli and pick up 2 L milk",
            LOCS,
        )
        types = [a["type"] for a in result["actions"]]
        assert "PICKUP" in types

    def test_milk_kappa_is_food(self):
        result = heuristic_parse(
            "Go to KMF Hubli and pick up 2 L milk",
            LOCS,
        )
        pickup = next(a for a in result["actions"] if a["type"] == "PICKUP")
        assert pickup["package_kappa"] == "FOOD"

    def test_milk_weight_correct(self):
        result = heuristic_parse(
            "Go to KMF Hubli and pick up 2 L milk",
            LOCS,
        )
        pickup = next(a for a in result["actions"] if a["type"] == "PICKUP")
        assert pickup["weight_kg"] == pytest.approx(2.0)

    def test_kmf_location_resolved(self):
        result = heuristic_parse(
            "Go to KMF Hubli and pick up 2 L milk",
            LOCS,
        )
        pickup = next(a for a in result["actions"] if a["type"] == "PICKUP")
        assert pickup["location"] == "KMF Hubli"

    def test_generic_dairy_instruction(self):
        # 'nandini' not in locations list but should resolve via full catalog
        result = heuristic_parse(
            "Collect 3 packets of nandini curd from nandini dairy",
            LOCS,
        )
        types = [a["type"] for a in result["actions"]]
        assert "PICKUP" in types
        pickup = next(a for a in result["actions"] if a["type"] == "PICKUP")
        assert pickup["package_kappa"] == "FOOD"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
