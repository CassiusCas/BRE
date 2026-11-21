"""Clip Census places, counties, and NCES districts to 50 miles of Birmingham.

Outputs compact GeoJSON the map loads. Census TIGER 2025 and NCES EDGE 2024-25.
"""

from __future__ import annotations

import json
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pyogrio
from pyproj import Transformer
from shapely import from_wkb, transform
from shapely.geometry import LineString, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data"

# Birmingham City Hall.
CENTER = (-86.8104, 33.5207)
MILES = 50
METERS = MILES * 1609.344

PLACE_URL = "https://www2.census.gov/geo/tiger/TIGER2025/PLACE/tl_2025_01_place.zip"
COUNTY_URL = "https://www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip"
DISTRICT_URL = "https://nces.ed.gov/programs/edge/data/EDGE_SCHOOLDISTRICT_TL25_SY2425.zip"

TO_M = Transformer.from_crs("EPSG:4269", "EPSG:26916", always_xy=True)
TO_LL = Transformer.from_crs("EPSG:26916", "EPSG:4269", always_xy=True)


def fetch(url: str, name: str) -> Path:
    dest = RAW / name
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "BRE birmingham map layer build"})
    with urllib.request.urlopen(req, timeout=180) as response:
        dest.write_bytes(response.read())
    return dest


def shp_in_zip(blob: Path) -> str:
    with zipfile.ZipFile(blob) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".shp")]
    if len(names) != 1:
        raise SystemExit(f"{blob.name} has shapefiles {names}")
    return f"/vsizip/{blob}/{names[0]}"


def _apply(transformer):
    def fn(coords):
        x, y = transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return fn


TO_M_FN = _apply(TO_M)
TO_LL_FN = _apply(TO_LL)


def as_metric(geom):
    return transform(geom, TO_M_FN)


def as_lonlat(geom):
    return transform(geom, TO_LL_FN)


# A little past 50 miles so a boundary that only nicks the circle is still read.
BBOX = (-87.8, 32.65, -85.8, 34.4)


def rows(path: str):
    meta, _fids, geometry, fields = pyogrio.raw.read(path, bbox=BBOX)
    names = list(meta["fields"])
    for index, geom in enumerate(geometry):
        if geom is None:
            continue
        values = {}
        for name, column in zip(names, fields):
            value = column[index]
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            elif hasattr(value, "item"):
                value = value.item()
            values[name] = value
        values["geometry"] = from_wkb(geom)
        yield values


def ring():
    point = as_metric(shape({"type": "Point", "coordinates": list(CENTER)}))
    return point.buffer(METERS)


def write(name: str, features: list[dict]) -> None:
    doc = {"type": "FeatureCollection", "features": features}
    path = OUT / name
    path.write_text(json.dumps(doc, separators=(",", ":")))
    print(name, len(features), path.stat().st_size)


def feature(geom, props: dict, simplify: float) -> dict | None:
    clipped = geom
    if clipped.is_empty:
        return None
    simple = as_lonlat(clipped.simplify(simplify, preserve_topology=True))
    if simple.is_empty:
        return None
    return {
        "type": "Feature",
        "properties": props,
        "geometry": mapping(simple),
    }


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    circle = ring()

    suburbs = []
    for row in rows(shp_in_zip(fetch(PLACE_URL, "al_place.zip"))):
        geom = as_metric(row["geometry"])
        if not geom.intersects(circle):
            continue
        piece = geom.intersection(circle)
        suburbs.append(
            feature(
                piece,
                {
                    "name": row["NAME"],
                    "label": row["NAMELSAD"],
                    "kind": "CDP" if str(row["LSAD"]) == "57" else "city",
                    "geoid": row["GEOID"],
                },
                80,
            )
        )
    suburbs = [item for item in suburbs if item]
    suburbs.sort(key=lambda item: item["properties"]["name"])
    write("suburbs.geojson", suburbs)

    county_features = []
    for row in rows(shp_in_zip(fetch(COUNTY_URL, "us_county.zip"))):
        geom = as_metric(row["geometry"])
        if not geom.intersects(circle):
            continue
        piece = geom.intersection(circle)
        county_features.append(
            feature(
                piece,
                {
                    "name": row["NAME"],
                    "label": f"{row['NAME']} County",
                    "state": row["STATEFP"],
                    "geoid": row["GEOID"],
                },
                120,
            )
        )
    county_features = [item for item in county_features if item]
    county_features.sort(key=lambda item: item["properties"]["name"])
    write("counties.geojson", county_features)

    district_features = []
    printed = False
    for row in rows(shp_in_zip(fetch(DISTRICT_URL, "districts.zip"))):
        if not printed:
            print("district columns", sorted(k for k in row if k != "geometry"))
            printed = True
        geom = row["geometry"]
        if geom is None or geom.is_empty:
            continue
        geom_m = as_metric(geom)
        if not geom_m.intersects(circle):
            continue
        piece = geom_m.intersection(circle)
        name = row.get("NAME") or ""
        low = row.get("LOGRADE") or ""
        high = row.get("HIGRADE") or ""
        district_features.append(
            feature(
                piece,
                {
                    "name": str(name).replace(" School District", "").strip(),
                    "label": str(name),
                    "grades": f"{low}–{high}".strip("–") if (low or high) else "",
                    "geoid": str(row.get("GEOID") or ""),
                },
                100,
            )
        )
    district_features = [item for item in district_features if item]
    district_features.sort(key=lambda item: item["properties"]["name"])
    write("districts.geojson", district_features)

    outline = LineString(as_lonlat(circle.exterior).coords)
    write(
        "radius.geojson",
        [
            {
                "type": "Feature",
                "properties": {"name": "50 miles of Birmingham"},
                "geometry": mapping(outline),
            }
        ],
    )


if __name__ == "__main__":
    main()
