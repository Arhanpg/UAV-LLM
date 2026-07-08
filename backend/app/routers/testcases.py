"""Curated test-case catalog for the UAV-LLM Mission Control UI.

Each case ships with pre-configured world parameters AND a natural-language
briefing so the operator can load it in one click and immediately run all
algorithms or interact via the NL chat.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["testcases"])

# Location index map (matches DHARWAD_LOCATIONS order in locations.py)
_L = {
    "SDM": 0, "KIMS": 1, "SURETECH": 2, "NAVODAYA": 3, "GOVT_HOSP": 4,
    "URBAN_OASIS": 5, "AKSHAY": 6, "BIG_BAZAAR_DWD": 7, "BIG_BAZAAR_HBL": 8,
    "RELIANCE_DWD": 9, "RELIANCE_HBL": 10,
    "KU": 11, "BVB": 12, "IIT": 13, "SANA": 14, "KARNATAK": 15,
    "DWD_RAIL": 16, "HBL_AIRPORT": 17, "HBL_RAIL": 18, "KSRTC_DWD": 19, "KSRTC_HBL": 20,
    "TOWN_HALL": 21, "GLASS_HOUSE": 22, "UNKAL": 23, "NRUPATUNGA": 24,
    "IND_AREA": 25, "ALMATTI": 26, "GOKUL": 27,
    "KMF_HBL": 28, "KMF_DWD": 29, "NANDINI": 30, "MOTHER_DAIRY": 31,
    "DC_OFFICE": 32, "HUMC": 33, "SIDDHAROODHA": 34,
}

TEST_CASES = [
    # -----------------------------------------------------------------------
    # EASY (1-2 stops, single commodity, no constraints)
    # -----------------------------------------------------------------------
    {
        "id": 1,
        "title": "TC-01: Single Pharma Delivery",
        "difficulty": "easy",
        "description": "Simple point-to-point insulin delivery from SDM Hospital to KIMS. "
                        "No hazards, no no-fly zones, tight deadline.",
        "loc_indices": [_L["SDM"], _L["KIMS"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "KIMS Hospital",
             "kappa": "PHARMA", "weight": 1.2, "description": "Insulin vials"},
        ],
        "nl_instruction": "Deliver insulin from SDM Hospital to KIMS urgently",
        "seed": 1, "n_gfz": 0, "incompat_density": 0.0,
        "deadline_tight": 0.8, "hazard_mix": 0.3, "cap_ratio": 0.6,
    },
    {
        "id": 2,
        "title": "TC-02: Milk Pickup from KMF",
        "difficulty": "easy",
        "description": "Fetch 2 L fresh milk from KMF Hubli and deliver to Urban Oasis Mall.",
        "loc_indices": [_L["SDM"], _L["KMF_HBL"], _L["URBAN_OASIS"]],
        "pkg_requests": [
            {"pickup_name": "KMF Hubli", "delivery_name": "Urban Oasis Mall",
             "kappa": "FOOD", "weight": 2.0, "description": "2L fresh milk"},
        ],
        "nl_instruction": "Go to KMF Hubli and pick up 2 L milk, then deliver to Urban Oasis Mall",
        "seed": 2, "n_gfz": 0, "incompat_density": 0.0,
        "deadline_tight": 0.4, "hazard_mix": 0.1, "cap_ratio": 0.5,
    },
    {
        "id": 3,
        "title": "TC-03: Electronics Drop",
        "difficulty": "easy",
        "description": "Deliver a laptop charger from BVB College to IIT Dharwad. Single stop.",
        "loc_indices": [_L["SDM"], _L["BVB"], _L["IIT"]],
        "pkg_requests": [
            {"pickup_name": "BVB College", "delivery_name": "IIT Dharwad",
             "kappa": "ELECTRONICS", "weight": 0.8, "description": "Laptop charger"},
        ],
        "nl_instruction": "Pick up the laptop charger from BVB and drop at IIT Dharwad",
        "seed": 3, "n_gfz": 0, "incompat_density": 0.0,
        "deadline_tight": 0.3, "hazard_mix": 0.0, "cap_ratio": 0.5,
    },
    {
        "id": 4,
        "title": "TC-04: Stationery to College",
        "difficulty": "easy",
        "description": "Deliver 3 notebooks to Sana Shaheen PU College. Pure GENERAL cargo.",
        "loc_indices": [_L["SDM"], _L["SANA"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "Sana Shaheen",
             "kappa": "GENERAL", "weight": 0.9, "description": "3 notebooks"},
        ],
        "nl_instruction": "Go through Sana Shaheen Independent PU College and give them 3 notebooks",
        "seed": 4, "n_gfz": 0, "incompat_density": 0.0,
        "deadline_tight": 0.2, "hazard_mix": 0.0, "cap_ratio": 0.5,
    },
    {
        "id": 5,
        "title": "TC-05: Multi-Stop Food Run",
        "difficulty": "easy",
        "description": "Pick up bread from Reliance and deliver to Karnataka University. Single carrier.",
        "loc_indices": [_L["SDM"], _L["RELIANCE_DWD"], _L["KU"]],
        "pkg_requests": [
            {"pickup_name": "Reliance Fresh Dharwad", "delivery_name": "Karnataka University",
             "kappa": "FOOD", "weight": 1.5, "description": "Bread and groceries"},
        ],
        "nl_instruction": "Collect bread from Reliance Fresh Dharwad and deliver to Karnataka University",
        "seed": 5, "n_gfz": 0, "incompat_density": 0.0,
        "deadline_tight": 0.3, "hazard_mix": 0.0, "cap_ratio": 0.5,
    },
    # -----------------------------------------------------------------------
    # MEDIUM (3-5 stops, mixed commodities, some constraints)
    # -----------------------------------------------------------------------
    {
        "id": 6,
        "title": "TC-06: Pharma + Food Multi-Drop",
        "difficulty": "medium",
        "description": "Carry insulin to KIMS and food package to Big Bazaar in one mission. "
                        "Incompatibility between PHARMA and FOOD must be handled.",
        "loc_indices": [_L["SDM"], _L["KIMS"], _L["SURETECH"], _L["BIG_BAZAAR_DWD"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "KIMS Hospital",
             "kappa": "PHARMA", "weight": 1.5, "description": "Insulin"},
            {"pickup_name": "SDM Hospital", "delivery_name": "Big Bazaar Dharwad",
             "kappa": "FOOD", "weight": 3.0, "description": "Groceries"},
        ],
        "nl_instruction": "Deliver insulin to KIMS first, then drop groceries at Big Bazaar",
        "seed": 6, "n_gfz": 1, "incompat_density": 0.2,
        "deadline_tight": 0.5, "hazard_mix": 0.3, "cap_ratio": 0.6,
    },
    {
        "id": 7,
        "title": "TC-07: No-Fly Zone Reroute",
        "difficulty": "medium",
        "description": "1 no-fly zone near KIMS forces HNP to reroute. Measures path inflation cost.",
        "loc_indices": [_L["SDM"], _L["KIMS"], _L["KU"], _L["DWD_RAIL"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "KIMS Hospital",
             "kappa": "PHARMA", "weight": 2.0, "description": "Medicines"},
            {"pickup_name": "SDM Hospital", "delivery_name": "Karnataka University",
             "kappa": "GENERAL", "weight": 1.0, "description": "Documents"},
        ],
        "nl_instruction": "Avoid the no-fly zone near KIMS and reroute to deliver medicines",
        "seed": 7, "n_gfz": 1, "incompat_density": 0.1,
        "deadline_tight": 0.6, "hazard_mix": 0.2, "cap_ratio": 0.6,
    },
    {
        "id": 8,
        "title": "TC-08: Dairy Cold-Chain",
        "difficulty": "medium",
        "description": "Cryogenic dairy sample from KMF to Navodaya Medical College. "
                        "Temperature constraint active: must stay 0-8 C.",
        "loc_indices": [_L["SDM"], _L["KMF_HBL"], _L["NAVODAYA"]],
        "pkg_requests": [
            {"pickup_name": "KMF Hubli", "delivery_name": "Navodaya Medical College",
             "kappa": "CRYOGENIC", "weight": 3.5, "description": "Cryo dairy sample"},
        ],
        "nl_instruction": "Pick up the cryo dairy sample from KMF Hubli and deliver to Navodaya under cold-chain",
        "seed": 8, "n_gfz": 0, "incompat_density": 0.0,
        "deadline_tight": 0.9, "hazard_mix": 0.5, "cap_ratio": 0.7,
    },
    {
        "id": 9,
        "title": "TC-09: Via Waypoint Delivery",
        "difficulty": "medium",
        "description": "Route must pass through Dharwad Railway Station before reaching KIMS. "
                        "Tests ADD_STOP and waypoint ordering.",
        "loc_indices": [_L["SDM"], _L["DWD_RAIL"], _L["KIMS"], _L["KU"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "KIMS Hospital",
             "kappa": "PHARMA", "weight": 1.8, "description": "Medical supplies"},
        ],
        "nl_instruction": "Go through Dharwad Railway Station first, then deliver to KIMS Hospital",
        "seed": 9, "n_gfz": 0, "incompat_density": 0.1,
        "deadline_tight": 0.5, "hazard_mix": 0.2, "cap_ratio": 0.6,
    },
    {
        "id": 10,
        "title": "TC-10: Flammable + Oxidizer Incompatibility",
        "difficulty": "medium",
        "description": "Fuel (FLAMMABLE) and O2 cylinder (OXIDIZER) must not be co-loaded. "
                        "Tests hard incompatibility enforcement.",
        "loc_indices": [_L["SDM"], _L["IND_AREA"], _L["ALMATTI"], _L["GOVT_HOSP"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "Dharwad Industrial Area",
             "kappa": "FLAMMABLE", "weight": 4.0, "description": "Fuel canister"},
            {"pickup_name": "Almatti Road Warehouse", "delivery_name": "Govt District Hospital",
             "kappa": "OXIDIZER", "weight": 5.0, "description": "O2 cylinder"},
        ],
        "nl_instruction": "Transport the fuel canister to Industrial Area, keep O2 cylinder separate",
        "seed": 10, "n_gfz": 0, "incompat_density": 0.4,
        "deadline_tight": 0.5, "hazard_mix": 0.8, "cap_ratio": 0.7,
    },
    # -----------------------------------------------------------------------
    # HARD (5+ stops, mixed hazards, geofences, tight deadlines)
    # -----------------------------------------------------------------------
    {
        "id": 11,
        "title": "TC-11: Hospital Hub Rush",
        "difficulty": "hard",
        "description": "4 hospitals, all PHARMA, 3 no-fly zones, tight 45-min deadlines. "
                        "Classic VRP stress test for HNP vs MPDD.",
        "loc_indices": [_L["SDM"], _L["KIMS"], _L["SURETECH"], _L["NAVODAYA"], _L["GOVT_HOSP"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "KIMS Hospital",
             "kappa": "PHARMA", "weight": 1.2, "description": "Insulin A"},
            {"pickup_name": "SDM Hospital", "delivery_name": "Suretech Hospital",
             "kappa": "PHARMA", "weight": 1.5, "description": "Vaccine batch"},
            {"pickup_name": "SDM Hospital", "delivery_name": "Navodaya Medical College",
             "kappa": "PHARMA", "weight": 2.0, "description": "Blood samples"},
            {"pickup_name": "SDM Hospital", "delivery_name": "Govt District Hospital",
             "kappa": "PHARMA", "weight": 1.8, "description": "Emergency meds"},
        ],
        "nl_instruction": "Emergency! Deliver all 4 pharma packages to the hospitals as fast as possible",
        "seed": 11, "n_gfz": 3, "incompat_density": 0.1,
        "deadline_tight": 0.9, "hazard_mix": 0.9, "cap_ratio": 0.7,
    },
    {
        "id": 12,
        "title": "TC-12: Cross-City Mixed Cargo",
        "difficulty": "hard",
        "description": "Dharwad -> Hubli cross-city run: PHARMA, FOOD, ELECTRONICS in one flight. "
                        "Tests semantic cost of mixed-commodity routing.",
        "loc_indices": [_L["SDM"], _L["KIMS"], _L["KMF_HBL"], _L["BVB"], _L["URBAN_OASIS"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "KIMS Hospital",
             "kappa": "PHARMA", "weight": 1.5, "description": "Medicines"},
            {"pickup_name": "KMF Hubli", "delivery_name": "Urban Oasis Mall",
             "kappa": "FOOD", "weight": 3.0, "description": "Dairy products"},
            {"pickup_name": "BVB College of Engg", "delivery_name": "IIT Dharwad",
             "kappa": "ELECTRONICS", "weight": 2.0, "description": "Robotics parts"},
        ],
        "nl_instruction": "Cross-city run: medicines to KIMS, dairy to Urban Oasis, electronics to BVB",
        "seed": 12, "n_gfz": 2, "incompat_density": 0.3,
        "deadline_tight": 0.6, "hazard_mix": 0.4, "cap_ratio": 0.6,
    },
    {
        "id": 13,
        "title": "TC-13: Emergency Mid-Flight Replan",
        "difficulty": "hard",
        "description": "Mission starts normally, then NL instruction adds emergency reroute "
                        "to avoid a pop-up no-fly zone. Tests live REROUTE action.",
        "loc_indices": [_L["SDM"], _L["KIMS"], _L["DWD_RAIL"], _L["KU"], _L["GOVT_HOSP"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "KIMS Hospital",
             "kappa": "PHARMA", "weight": 2.0, "description": "Critical insulin"},
            {"pickup_name": "SDM Hospital", "delivery_name": "Govt District Hospital",
             "kappa": "GENERAL", "weight": 1.0, "description": "Documents"},
        ],
        "nl_instruction": "Emergency no-fly zone detected near KIMS! Reroute via Dharwad Railway Station",
        "seed": 13, "n_gfz": 2, "incompat_density": 0.2,
        "deadline_tight": 0.8, "hazard_mix": 0.3, "cap_ratio": 0.6,
    },
    {
        "id": 14,
        "title": "TC-14: Split Delivery Cold-Chain",
        "difficulty": "hard",
        "description": "Insulin must reach a zone only accessible by ground agent (hospital courtyard). "
                        "Tests SPLIT_DELIVERY handoff at boundary.",
        "loc_indices": [_L["SDM"], _L["KIMS"], _L["SURETECH"], _L["NAVODAYA"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "Navodaya Medical College",
             "kappa": "CRYOGENIC", "weight": 4.0, "description": "Cryogenic insulin"},
            {"pickup_name": "SDM Hospital", "delivery_name": "Suretech Hospital",
             "kappa": "PHARMA", "weight": 1.5, "description": "Vaccines"},
        ],
        "nl_instruction": "Navodaya is blocked, hand off the cryo insulin to a ground agent at the boundary",
        "seed": 14, "n_gfz": 1, "incompat_density": 0.2,
        "deadline_tight": 0.9, "hazard_mix": 0.6, "cap_ratio": 0.65,
    },
    {
        "id": 15,
        "title": "TC-15: Maximum Incompatibility Stress",
        "difficulty": "hard",
        "description": "FLAMMABLE + OXIDIZER + PHARMA in same mission. "
                        "incompat_density=0.4. Tests feasibility under maximum constraint pressure.",
        "loc_indices": [_L["SDM"], _L["IND_AREA"], _L["ALMATTI"], _L["GOVT_HOSP"], _L["KIMS"]],
        "pkg_requests": [
            {"pickup_name": "SDM Hospital", "delivery_name": "Dharwad Industrial Area",
             "kappa": "FLAMMABLE", "weight": 5.0, "description": "Fuel"},
            {"pickup_name": "Almatti Road Warehouse", "delivery_name": "Govt District Hospital",
             "kappa": "OXIDIZER", "weight": 5.0, "description": "O2"},
            {"pickup_name": "SDM Hospital", "delivery_name": "KIMS Hospital",
             "kappa": "PHARMA", "weight": 1.5, "description": "Insulin"},
        ],
        "nl_instruction": "Handle all three packages, keep hazmat separated from insulin at all times",
        "seed": 15, "n_gfz": 2, "incompat_density": 0.4,
        "deadline_tight": 0.7, "hazard_mix": 0.9, "cap_ratio": 0.7,
    },
    # -----------------------------------------------------------------------
    # EXPERT (full city, 6+ stops, all constraints active)
    # -----------------------------------------------------------------------
    {
        "id": 16,
        "title": "TC-16: Full Dharwad City Run",
        "difficulty": "expert",
        "description": "All 6 Dharwad city nodes active. Auto-generated packages. "
                        "3 no-fly zones. Deadline tight=0.7. Benchmark for HNP paper.",
        "loc_indices": [_L["SDM"], _L["KIMS"], _L["KU"], _L["DWD_RAIL"],
                        _L["GOVT_HOSP"], _L["SANA"]],
        "pkg_requests": [],
        "nl_instruction": "Run full Dharwad city mission with auto packages",
        "seed": 16, "n_gfz": 3, "incompat_density": 0.3,
        "deadline_tight": 0.7, "hazard_mix": 0.5, "cap_ratio": 0.65,
    },
    {
        "id": 17,
        "title": "TC-17: Dharwad-Hubli Corridor",
        "difficulty": "expert",
        "description": "8 nodes spanning both cities. Mixed PHARMA+FOOD+ELECTRONICS. "
                        "Wind 15 m/s. Maximum semantic cost mission.",
        "loc_indices": [_L["SDM"], _L["KIMS"], _L["KMF_HBL"], _L["BVB"],
                        _L["URBAN_OASIS"], _L["HBL_RAIL"], _L["IIT"], _L["GOVT_HOSP"]],
        "pkg_requests": [],
        "nl_instruction": "Full corridor mission: hospitals, malls and colleges across Dharwad-Hubli",
        "seed": 17, "n_gfz": 4, "incompat_density": 0.35,
        "deadline_tight": 0.75, "hazard_mix": 0.55, "cap_ratio": 0.6,
    },
    {
        "id": 18,
        "title": "TC-18: Adversarial Max-Stress",
        "difficulty": "expert",
        "description": "12 nodes, incompat_density=0.45, n_gfz=5, deadline_tight=0.9. "
                        "Designed to break weaker algorithms. Use to compare HNP vs all.",
        "loc_indices": [_L["SDM"], _L["KIMS"], _L["SURETECH"], _L["NAVODAYA"],
                        _L["GOVT_HOSP"], _L["KMF_HBL"], _L["BVB"], _L["IIT"],
                        _L["URBAN_OASIS"], _L["HBL_RAIL"], _L["IND_AREA"], _L["ALMATTI"]],
        "pkg_requests": [],
        "nl_instruction": "Maximum stress test: all nodes, tightest constraints, adversarial geofences",
        "seed": 42, "n_gfz": 5, "incompat_density": 0.45,
        "deadline_tight": 0.9, "hazard_mix": 0.8, "cap_ratio": 0.55,
    },
]


@router.get("/test-cases")
def list_test_cases():
    """Return all curated test cases for the UI."""
    return {"count": len(TEST_CASES), "test_cases": TEST_CASES}


@router.get("/test-cases/{tc_id}")
def get_test_case(tc_id: int):
    for tc in TEST_CASES:
        if tc["id"] == tc_id:
            return tc
    return {"error": f"test case {tc_id} not found"}
