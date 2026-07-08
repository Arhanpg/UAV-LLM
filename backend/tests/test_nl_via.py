"""Tests for via/waypoint parsing and kappa sanitization."""

import pytest

from app.llm.nl_mission_parser import _sanitize_kappa, heuristic_parse

LOCS = [
    "SDM Hospital & Medical College",
    "KIMS Hospital Dharwad",
    "Sana Shaheen Independent PU College",
    "Dharwad Railway Station",
    "Karnataka University",
]


class TestSanitizeKappa:
    def test_valid_classes_pass_through(self):
        for cls in ("PHARMA", "FOOD", "ELECTRONICS", "FLAMMABLE", "OXIDIZER", "CRYOGENIC", "GENERAL"):
            assert _sanitize_kappa(cls) == cls

    def test_notebook_maps_to_general(self):
        assert _sanitize_kappa("3 notebooks") == "GENERAL"
        assert _sanitize_kappa("notebook") == "GENERAL"

    def test_insulin_maps_to_pharma(self):
        assert _sanitize_kappa("insulin vials") == "PHARMA"

    def test_none_maps_to_general(self):
        assert _sanitize_kappa(None) == "GENERAL"
        assert _sanitize_kappa("") == "GENERAL"

    def test_unknown_maps_to_general(self):
        assert _sanitize_kappa("random stuff xyz") == "GENERAL"


class TestViaWaypoint:
    def test_go_through_emits_add_stop(self):
        result = heuristic_parse(
            "So go through Sana Shaheen Independent PU College and give them 3 notebooks",
            LOCS,
        )
        actions = result["actions"]
        types = [a["type"] for a in actions]
        assert "ADD_STOP" in types, f"Expected ADD_STOP in {types}"
        stop = next(a for a in actions if a["type"] == "ADD_STOP")
        assert stop["location"] == "Sana Shaheen Independent PU College"

    def test_deliver_also_emitted(self):
        result = heuristic_parse(
            "So go through Sana Shaheen Independent PU College and give them 3 notebooks",
            LOCS,
        )
        types = [a["type"] for a in result["actions"]]
        assert "DELIVER" in types, f"Expected DELIVER in {types}"

    def test_kappa_is_valid_class(self):
        result = heuristic_parse(
            "So go through Sana Shaheen Independent PU College and give them 3 notebooks",
            LOCS,
        )
        from app.config import CLASSES

        for act in result["actions"]:
            assert act["package_kappa"] in CLASSES, f"Invalid kappa: {act['package_kappa']}"

    def test_via_with_known_location(self):
        result = heuristic_parse(
            "Go via Karnataka University and deliver insulin to KIMS Hospital Dharwad",
            LOCS,
        )
        types = [a["type"] for a in result["actions"]]
        assert "ADD_STOP" in types

    def test_quantity_extracted(self):
        result = heuristic_parse(
            "Deliver 5 packages to Dharwad Railway Station",
            LOCS,
        )
        deliver_act = next((a for a in result["actions"] if a["type"] == "DELIVER"), None)
        assert deliver_act is not None
        assert deliver_act.get("quantity") == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
