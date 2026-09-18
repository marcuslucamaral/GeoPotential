"""Coordinate reference systems.

There is no default CRS. A source without one stops the run with a message
naming the source (ADR-004, and defect D-02 of the legacy tree, where
`EPSG:31982` was a silent `.get()` fallback in three modules).
"""
from __future__ import annotations

from dataclasses import dataclass

from pyproj import CRS


class MissingCrsError(ValueError):
    """A source carried no CRS. Named, never guessed."""


class NotMetricError(ValueError):
    """A metric operation was asked for on a geographic CRS."""


@dataclass(frozen=True)
class CrsInfo:
    """A coordinate reference system, with the unit it measures in.

    Constructed from anything pyproj accepts. `unit` is the linear unit of the
    axes — `metre`, `degree`, `US survey foot` — and is what a pixel size or a
    distance is expressed in. Reading it from the CRS rather than assuming it
    is what stops a control labelled `m` from sitting next to a geographic CRS.
    """

    crs: CRS

    @classmethod
    def from_user_input(cls, value: object, *, source: str) -> "CrsInfo":
        """Build from an EPSG code, WKT, PROJ string or pyproj CRS.

        value    the CRS as declared by the source; None or "" is refused
        source   the dataset name, used in the error message
        returns  CrsInfo
        raises   MissingCrsError when value is absent or unparseable
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            raise MissingCrsError(
                f"{source}: no CRS declared. Declare one; there is no default."
            )
        try:
            return cls(CRS.from_user_input(value))
        except Exception as exc:
            raise MissingCrsError(f"{source}: CRS {value!r} is not usable: {exc}") from exc

    @property
    def is_geographic(self) -> bool:
        return bool(self.crs.is_geographic)

    @property
    def unit(self) -> str:
        """Linear (or angular) unit of the first axis, as the CRS declares it."""
        axis = self.crs.axis_info
        return axis[0].unit_name if axis else "unknown"

    @property
    def epsg(self) -> str | None:
        code = self.crs.to_epsg()
        return f"EPSG:{code}" if code else None

    @property
    def name(self) -> str:
        return self.epsg or self.crs.name

    def require_metric(self, operation: str) -> None:
        """Refuse a metric operation on a geographic CRS.

        operation  what was asked for, named in the error
        raises     NotMetricError on a geographic CRS

        Euclidean distance, pixel size in metres and IDW search radii are
        meaningless in degrees. Producing degrees labelled as metres is the
        failure mode this exists to stop.
        """
        if self.is_geographic:
            raise NotMetricError(
                f"{operation} needs a projected CRS; {self.name} is geographic "
                f"and measures in {self.unit}. Reproject first."
            )

    def to_wkt(self) -> str:
        return self.crs.to_wkt()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CrsInfo) and self.crs.equals(other.crs)

    def __hash__(self) -> int:
        return hash(self.crs.to_wkt())

    def __repr__(self) -> str:
        return f"CrsInfo({self.name}, unit={self.unit})"
