"""RecorderSource ABC — Placer CountyFusion today; Sacramento later."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RecorderRow:
    doc_number: str
    names: str = ""
    other_party: str = ""
    doc_type: str = ""
    record_date: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class RecorderSearchResult:
    query: str
    rows: list[RecorderRow]
    truncated: bool = False
    page_count: int = 0
    cached: bool = False

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "truncated": self.truncated,
            "page_count": self.page_count,
            "cached": self.cached,
            "rows": [r.to_dict() for r in self.rows],
        }


class RecorderSource(ABC):
    """County recorder index search interface."""

    name: str = "abstract"

    @abstractmethod
    def search_name(
        self,
        name: str,
        *,
        from_date: str = "01/01/1980",
        refresh: bool = False,
    ) -> RecorderSearchResult:
        """Search the public index by name. Cache-first when implemented."""

    def close(self) -> None:
        """Release browser / HTTP resources."""
