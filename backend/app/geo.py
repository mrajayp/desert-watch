"""Minimal GeoJSON helpers (no GIS dependency): polygon centroids for placing
region nodes on the map."""
import json
from pathlib import Path


def _rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [p[0] for p in geom["coordinates"]]
    return []


def centroid(geom) -> tuple[float, float]:
    """Area-weighted centroid of the outer rings, returned as (lat, lon)."""
    a = cx = cy = 0.0
    for ring in _rings(geom):
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            c = x0 * y1 - x1 * y0
            a += c
            cx += (x0 + x1) * c
            cy += (y0 + y1) * c
    if a == 0:
        x, y = _rings(geom)[0][0]
        return y, x
    return cy / (3 * a), cx / (3 * a)


def centroids_by_name(path: Path) -> dict[str, tuple[float, float]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {f["properties"]["shapeName"]: centroid(f["geometry"]) for f in data["features"]}
