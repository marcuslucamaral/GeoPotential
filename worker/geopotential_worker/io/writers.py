"""Atomic artefact writing.

Section 30 of the implementation document: an artefact is written .tmp, then
flushed, closed, validated, hashed, renamed, and only then registered. Never
register as valid a file still being written.

Every GeoTIFF written declares its nodata. A raster written with nodata=None
while its array carries NaN is a contract violation — defect D-05, present at
all four `save_geotiff` call sites of the legacy tree.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

from ..domain.grid import TargetGrid

CHUNK = 1 << 20  # 1 MiB, for hashing without holding the file in memory


@dataclass(frozen=True)
class Artifact:
    """A closed, validated, hashed file. The only thing a run may register."""

    path: Path
    type: str
    hash: str
    bytes: int

    def as_message_fields(self, artifact_id: str) -> dict[str, object]:
        """Body of a `job_artifact` message.

        The format is `artifact_type`, not `type`: the protocol envelope owns
        `type` as the message kind. See `protocol.REQUIRED[JOB_ARTIFACT]`.
        """
        return {
            "artifact_id": artifact_id,
            "path": str(self.path),
            "artifact_type": self.type,
            "hash": self.hash,
            "bytes": self.bytes,
        }


def sha256_file(path: Path) -> str:
    """Content hash of a closed file, as `sha256:<hex>`."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def write_geotiff(
    values: np.ndarray,
    grid: TargetGrid,
    path: Path,
    *,
    tags: dict[str, str] | None = None,
    compress: str = "deflate",
    overwrite: bool = False,
) -> Artifact:
    """Write one float32 band atomically, with nodata declared as NaN.

    values     (grid.height, grid.width) float32; NaN is the null
    grid       the target grid; supplies transform and CRS
    path       final destination; the temporary file sits beside it
    tags       GeoTIFF metadata written to the default namespace
    overwrite  replace a file that is already there. Off by default.
    returns    Artifact — path, type, hash, size — after the rename
    raises     FileExistsError when `path` exists and `overwrite` is False

    The file is validated by reopening it and checking that the declared
    nodata, the CRS, the transform and the shape survived the round trip.
    A clean write is not evidence that the file is readable.

    **An output is never silently overwritten** (`P-24`). That was enforced
    only at the Project Store, by the `artifact.path` UNIQUE constraint, and
    the writer itself replaced whatever was there. In the application the two
    never met, because every run writes into its own directory — so the hole
    was invisible until a harness ran two operations into one directory and
    measured the second one's output believing it was the first's.

    The store's constraint stays; this is the same rule one layer lower, where
    the bytes actually reach the disk. `overwrite=True` exists for the caller
    that means it, and it has to say so.
    """
    if values.shape != grid.shape:
        raise ValueError(f"values are {values.shape}, grid is {grid.shape}")
    if values.dtype != np.float32:
        raise TypeError(f"values must be float32, got {values.dtype}")

    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"{path} already exists. An output is never silently overwritten "
            f"(P-24): the file there was produced by something, and replacing "
            f"it would destroy an artefact no rebuild reproduces. Write to "
            f"another name, or pass overwrite=True and mean it."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")

    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "width": grid.width,
        "height": grid.height,
        "crs": grid.crs.crs,
        "transform": grid.transform,
        "nodata": float("nan"),
        "compress": compress,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }

    try:
        with rasterio.open(tmp, "w", **profile) as dst:
            dst.write(values, 1)
            if tags:
                dst.update_tags(**tags)
        # flush and close have happened; force the bytes to the device before
        # the rename, or a crash can publish a name pointing at a short file.
        fd = os.open(tmp, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

        _validate_geotiff(tmp, grid)
        digest = sha256_file(tmp)
        size = tmp.stat().st_size
        os.replace(tmp, path)  # atomic within a filesystem
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    return Artifact(path=path, type="GeoTIFF", hash=digest, bytes=size)


def _validate_geotiff(path: Path, grid: TargetGrid) -> None:
    """Reopen and check that what was asked for is what is on disk.

    raises  ValueError naming the first field that disagrees
    """
    with rasterio.open(path) as src:
        if (src.height, src.width) != grid.shape:
            raise ValueError(
                f"{path.name}: wrote {grid.shape} but reads back "
                f"{(src.height, src.width)}"
            )
        if src.nodata is None or not np.isnan(src.nodata):
            raise ValueError(
                f"{path.name}: nodata reads back as {src.nodata!r}; NaN is the "
                f"single null and every GeoTIFF must declare it"
            )
        if src.crs is None:
            raise ValueError(f"{path.name}: no CRS on disk")
        if not grid.crs.crs.equals(src.crs):
            raise ValueError(
                f"{path.name}: CRS reads back as {src.crs}, expected "
                f"{grid.crs.name}"
            )
        if tuple(src.transform)[:6] != tuple(grid.transform)[:6]:
            raise ValueError(f"{path.name}: transform does not round-trip")
