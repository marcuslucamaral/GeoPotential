"""Distance to the nearest feature. No interpolation anywhere in here.

inputs   a boolean mask of the cells a feature occupies, and the pixel size
output   float32 distance in the CRS's unit, 0 on the feature itself
reference  Felzenszwalb & Huttenlocher (2012), the exact linear-time distance
           transform `scipy.ndimage` implements.

This is how a `Distance to fault` criterion is made: a fault line is a fact,
and the distance to it is another fact. Nothing is estimated — which is why it
is not interpolation and must not be described as one.

**Anisotropic pixels are carried through.** `distance_transform_edt` takes a
`sampling` per axis; averaging the two into one scalar is silently wrong on
every grid that is not square, and wrong by more the more elongated it is.
"""
from __future__ import annotations

import numpy as np


def to_features(
    mask: np.ndarray,
    pixel_size: tuple[float, float],
    *,
    max_distance: float | None = None,
) -> np.ndarray:
    """Distance from every cell to the nearest True cell of `mask`.

    mask         (h, w) boolean; True where a feature is
    pixel_size   (px, py) in the CRS's unit — both, never averaged
    max_distance beyond it the answer is NaN rather than a number nobody
                 asked for; the cap is recorded in the manifest
    returns      (h, w) float32, 0 on a feature, NaN where nothing is near

    An empty mask gives an all-NaN grid, not zeros: "no feature anywhere" is
    not "the feature is everywhere", and zero would read as the latter.
    """
    from scipy import ndimage

    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return np.full(mask.shape, np.nan, dtype=np.float32)

    px, py = float(pixel_size[0]), float(pixel_size[1])
    if px <= 0 or py <= 0:
        raise ValueError(f"pixel size must be positive; got {px} x {py}")

    # `sampling` is (row spacing, column spacing) — rows run north-south, so
    # it is (py, px) and not (px, py). Swapping them transposes the anisotropy
    # and produces distances that are wrong everywhere except a square pixel.
    distance = ndimage.distance_transform_edt(~mask, sampling=(py, px))
    distance = distance.astype(np.float32)

    if max_distance is not None:
        if not np.isfinite(max_distance) or max_distance <= 0:
            raise ValueError(
                f"max_distance must be a positive number; got {max_distance}")
        distance = np.where(distance > max_distance, np.nan, distance)
    return distance


def statistics(values: np.ndarray) -> dict[str, float | int | None]:
    """What the manifest records about the distance field."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"valid": 0, "valid_fraction": 0.0,
                "min": None, "max": None, "mean": None}
    return {
        "valid": int(finite.size),
        "valid_fraction": float(finite.size / values.size),
        "min": float(finite.min()),
        "max": float(finite.max()),
        "mean": float(finite.mean(dtype=np.float64)),
    }
