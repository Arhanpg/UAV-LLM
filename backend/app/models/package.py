from dataclasses import dataclass


@dataclass
class Package:
    idx: int
    pickup_loc: int
    delivery_loc: int
    weight: float
    kappa: str
    deadline: float
    priority: float
    temp_required: bool
    description: str = ""
