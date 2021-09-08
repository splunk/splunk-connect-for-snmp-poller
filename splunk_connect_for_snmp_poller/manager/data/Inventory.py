from dataclasses import dataclass


@dataclass
class Inventory:
    host: str
    version: str
    community: str
    profile: str
    freqinseconds: str
