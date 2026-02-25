# models_cases.py
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any

@dataclass
class CaseData:
    name: str

    trajectory_rows: List[List[str]] = field(default_factory=list)
    casing_rows: List[List[str]] = field(default_factory=list)
    openhole_rows: List[List[str]] = field(default_factory=list)
    bha_rows: List[List[str]] = field(default_factory=list)
    fluids_rows: List[List[str]] = field(default_factory=list)

    altitude: float = 0.0
    azim_corr: float = 0.0


@dataclass
class WellNode:
    name: str
    cases: List[CaseData] = field(default_factory=list)


@dataclass
class FieldNode:
    name: str
    wells: List[WellNode] = field(default_factory=list)


@dataclass
class ProjectNode:
    name: str
    fields: List[FieldNode] = field(default_factory=list)


@dataclass
class ProjectStore:
    projects: List[ProjectNode] = field(default_factory=list)


def store_to_dict(store: ProjectStore) -> Dict[str, Any]:
    """Для сохранения в JSON."""
    return asdict(store)
