#!/usr/bin/env python3
"""Neighborhood boundaries for the close-in Birmingham suburbs.

Birmingham's neighborhoods come from the city GIS. The surrounding cities
within about 20 miles do not publish neighborhood polygons. Where The Move
Genie names a prominent area, this script dissolves the matching county
parcel neighborhoods and clips them to the city limit.

Colors on the suburb and county files are chosen so shapes that touch do
not share a fill.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import transform, unary_union
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
USER_AGENT = "birmingham-map/0.1 (house-shopping map)"

JEFF = "https://jccgis.jccal.org/server/rest/services/Basemap/Parcels/MapServer/0/query"
SHELBY = "https://maps.shelbyal.com/gisserver/rest/services/LegacyServices/ShelbyALWebIdentify/MapServer/1/query"
BIRMINGHAM = "https://gisweb.birminghamal.gov/arcgis/rest/services/Neighborhood/MapServer/0/query"

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32616", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:32616", "EPSG:4326", always_xy=True)

# Pastels far enough apart to read as different cities, with a darker edge.
PALETTE = [
    ("#e7c4a0", "#8a5a32"),
    ("#b7d7a8", "#3d6b3a"),
    ("#f0c2c0", "#8d4548"),
    ("#b9ccee", "#3d5f92"),
    ("#e6d48a", "#7a6420"),
    ("#d2c2ea", "#5c4a86"),
    ("#a9ddd2", "#2d6d64"),
    ("#f3c59a", "#8a5528"),
    ("#c5dce8", "#3e6478"),
    ("#e8c8b0", "#7a5340"),
    ("#cfe8b4", "#547236"),
    ("#f0c6dc", "#8a4570"),
    ("#d8c4a4", "#6e5434"),
    ("#c9e0c4", "#3f6848"),
    ("#e8d0c8", "#7a564c"),
    ("#c8d4c8", "#4d5e4e"),
]

# city, name, service, where. Clipped to that city's census limit.
TARGETS = [
    ("Hoover", "Bluff Park", "jeff", "NbhName='BLUFF PARK'"),
    ("Hoover", "Riverchase", "jeff", "NbhName IN ('RIVERCHASE','RIVERCHASE C C')"),
    ("Hoover", "Trace Crossings", "jeff", "NbhName='TRACE CROSSINGS'"),
    ("Hoover", "Ross Bridge", "jeff", "NbhName IN ('ROSS BRIDGE','VALLEY ROSS BRI')"),
    ("Hoover", "Green Valley", "jeff", "NbhName IN ('GREEN VALLEY','GREEN VALLEY FW')"),
    ("Hoover", "Greystone", "shelby", "UPPER(Subd_Name) LIKE '%GREYSTONE%' OR UPPER(SUBD_NAME_1) LIKE '%GREYSTONE%'"),
    ("Hoover", "Inverness", "shelby", "UPPER(Subd_Name) LIKE '%INVERNESS%' OR UPPER(SUBD_NAME_1) LIKE '%INVERNESS%'"),
    ("Vestavia Hills", "Rocky Ridge", "jeff", "NbhName='ROCKY RIDGE'"),
    ("Vestavia Hills", "Liberty Park", "jeff", "NbhName LIKE 'LIBERTY PARK%'"),
    ("Vestavia Hills", "Cahaba Heights", "jeff", "NbhName IN ('CAHABA HEIGHTS','CAHABA HGTS')"),
    ("Vestavia Hills", "Altadena", "jeff", "NbhName LIKE 'ALTADENA%'"),
    ("Vestavia Hills", "Dolly Ridge", "jeff", "NbhName LIKE 'DOLLY RIDGE%'"),
    ("Homewood", "Edgewood", "jeff", "NbhName='EAST EDGEWOOD'"),
    ("Homewood", "West Homewood", "jeff", "NbhName='WEST EDGEWOOD'"),
    ("Homewood", "Hollywood", "jeff", "NbhName IN ('HOLLYWOOD C CLB','HOLLYWOOD VILLA')"),
    ("Homewood", "Rosedale", "jeff", "NbhName='ROSEDALE'"),
    ("Homewood", "Mayfair", "jeff", "NbhName='MAYFAIR'"),
    ("Homewood", "Edgemont", "jeff", "NbhName IN ('EDGEMONT PARK','EDGEMONT TOWNHOMES')"),
    ("Homewood", "Lakeshore", "jeff", "NbhName='NORTH LAKESHORE'"),
    ("Mountain Brook", "English Village", "jeff", "NbhName='ENGLISH VILLAGE'"),
    ("Mountain Brook", "Crestline", "jeff", "NbhName IN ('CRESTLINE HTS','CRESTLINE HEIGHTS SOUTH','CRESTLINE VILLA','EAST CRESTLINE')"),
    ("Mountain Brook", "Cherokee Bend", "jeff", "NbhName='CHEROKEE BEND'"),
    ("Mountain Brook", "Overton", "jeff", "NbhName IN ('OVERTON','OVERTON MANOR')"),
    ("Mountain Brook", "Cahaba Village", "jeff", "NbhName='CAHABA VILLAGE'"),
    ("Trussville", "Carrington Lakes", "jeff", "NbhName='CARRINGTON'"),
    ("Trussville", "Stockton", "jeff", "NbhName='STOCKTON'"),
    ("Trussville", "Longmeadow", "jeff", "NbhName='LONGMEADOW'"),
    ("Trussville", "The Crossings at Deerfoot", "jeff", "NbhName='CROSSINGS AT DEERFOOT'"),
    ("Trussville", "Trussville Springs", "jeff", "NbhName='TRUSSVILLE SPRINGS'"),
    ("Irondale", "Rock Ridge", "jeff", "NbhName='ROCK RIDGE'"),
    ("Irondale", "Liberty Highlands", "jeff", "NbhName='LIBERTY HGLDS'"),
    ("Irondale", "Crestline Gardens", "jeff", "NbhName='C''LINE HOL GDNS'"),
    ("Gardendale", "Longwood", "jeff", "NbhName='LONGWOOD'"),
    ("Gardendale", "Fieldstown Crossing", "jeff", "NbhName='FIELDSTOWN CROSSING'"),
    ("Gardendale", "Magnolia Ridge", "jeff", "NbhName='MAGNOLIA RIDGE'"),
    ("Gardendale", "Turnberry", "jeff", "NbhName='TURNBERRY'"),
    ("Leeds", "Grand River", "jeff", "NbhName='GRAND RIVER'"),
    ("Helena", "Hillsboro", "shelby", "UPPER(Subd_Name) LIKE '%HILLSBORO%' OR UPPER(SUBD_NAME_1) LIKE '%HILLSBORO%'"),
    ("Helena", "Dearing Downs", "shelby", "UPPER(Subd_Name) LIKE '%DEARING%' OR UPPER(SUBD_NAME_1) LIKE '%DEARING%'"),
    ("Helena", "Riverwoods", "shelby", "UPPER(Subd_Name) LIKE '%RIVERWOOD%' OR UPPER(SUBD_NAME_1) LIKE '%RIVERWOOD%'"),
    ("Helena", "Wyndham", "shelby", "UPPER(Subd_Name) LIKE '%WYNDHAM%' OR UPPER(SUBD_NAME_1) LIKE '%WYNDHAM%'"),
    ("Helena", "Old Cahaba", "shelby", "UPPER(Subd_Name) LIKE '%OLD CAHABA%' OR UPPER(SUBD_NAME_1) LIKE '%OLD CAHABA%'"),
    ("Pelham", "Ballantrae", "shelby", "UPPER(Subd_Name) LIKE '%BALLANTRAE%' OR UPPER(SUBD_NAME_1) LIKE '%BALLANTRAE%'"),
    ("Pelham", "Oak Mountain Estates", "shelby", "UPPER(Subd_Name) LIKE '%OAK MOUNTAIN%' OR UPPER(SUBD_NAME_1) LIKE '%OAK MOUNTAIN%'"),
    ("Pelham", "Hunters Ridge", "shelby", "UPPER(Subd_Name) LIKE '%HUNTERS RIDGE%' OR UPPER(Subd_Name) LIKE '%HUNTER''S RIDGE%' OR UPPER(SUBD_NAME_1) LIKE '%HUNTERS RIDGE%'"),
]

SOURCE = {
    "jeff": "Jefferson County parcel neighborhoods, clipped to the city limit",
    "shelby": "Shelby County subdivisions, clipped to the city limit",
    "birmingham": "City of Birmingham neighborhood boundaries",
}


def log(message: str) -> None:
    print(message, flush=True)


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode())


def ring_area(ring: list) -> float:
    area = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        area += x1 * y2 - x2 * y1
    return area / 2


def esri_to_shape(geom: dict | None):
    if not geom or not geom.get("rings"):
        return None
    shells = []
    holes = []
    for ring in geom["rings"]:
        if len(ring) < 4:
            continue
        # Esri outer rings are clockwise, so the shoelace area is negative.
        if ring_area(ring) < 0:
            shells.append(ring)
        else:
            holes.append(ring)
    if not shells:
        shells = holes
        holes = []
    polygons = []
    for shell in shells:
        shell_poly = Polygon(shell)
        if not shell_poly.is_valid:
            shell_poly = make_valid(shell_poly)
        owned = [hole for hole in holes if shell_poly.contains(Polygon(hole).representative_point())]
        poly = Polygon(shell, owned)
        polygons.append(make_valid(poly))
    if not polygons:
        return None
    merged = unary_union(polygons)
    return make_valid(merged)


def fetch_where(endpoint: str, where: str):
    parts = []
    offset = 0
    while True:
        query = urllib.parse.urlencode({
            "where": where,
            "outFields": "OBJECTID",
            "returnGeometry": "true",
            "outSR": "4326",
            "maxAllowableOffset": "0.00018",
            "f": "json",
            "resultOffset": str(offset),
            "resultRecordCount": "2000",
        })
        payload = get_json(endpoint + "?" + query)
        if payload.get("error"):
            raise RuntimeError(payload["error"])
        batch = payload.get("features") or []
        for feature in batch:
            geom = esri_to_shape(feature.get("geometry"))
            if geom is not None and not geom.is_empty:
                parts.append(geom)
        if not payload.get("exceededTransferLimit"):
            break
        offset += len(batch)
        if not batch:
            break
    if not parts:
        return None
    return make_valid(unary_union(parts))


def project(geom, transformer):
    return transform(transformer.transform, geom)


def km2(geom) -> float:
    return project(geom, TO_UTM).area / 1_000_000


def round_geom(geom, digits: int = 5):
    def _round(x, y, z=None):
        return (round(x, digits), round(y, digits))
    return transform(_round, geom)


def feature(name: str, city: str, source: str, geom, note: str) -> dict:
    geom = make_valid(geom)
    point = geom.representative_point()
    return {
        "type": "Feature",
        "properties": {
            "name": name,
            "city": city,
            "source": source,
            "note": note,
            "area_km2": round(km2(geom), 2),
            "label": [round(point.y, 5), round(point.x, 5)],
        },
        "geometry": mapping(round_geom(geom)),
    }


def load_cities() -> dict:
    places = json.loads((DATA / "places.geojson").read_text())
    cities = {}
    for item in places["features"]:
        cities[item["properties"]["name"]] = make_valid(shape(item["geometry"]))
    return cities


def polygonal(geom):
    geom = make_valid(geom)
    if geom.geom_type == "GeometryCollection":
        kept = [part for part in geom.geoms if part.geom_type in ("Polygon", "MultiPolygon")]
        geom = unary_union(kept) if kept else Polygon()
    if geom.is_empty:
        return geom
    return make_valid(geom.buffer(0))


def paint(features: list[dict]) -> None:
    geoms = [polygonal(shape(item["geometry"])) for item in features]
    order = sorted(range(len(features)), key=lambda index: geoms[index].area, reverse=True)
    chosen = [None] * len(features)
    for index in order:
        used = set()
        for other, color in enumerate(chosen):
            if color is None or geoms[index].is_empty or geoms[other].is_empty:
                continue
            try:
                touches = geoms[index].intersects(geoms[other])
            except Exception:
                touches = False
            if touches:
                used.add(color)
        pick = 0
        while pick in used and pick < len(PALETTE) - 1:
            pick += 1
        if pick in used:
            pick = min(range(len(PALETTE)), key=lambda color: sum(1 for item in chosen if item == color))
        chosen[index] = pick
    for item, color in zip(features, chosen):
        fill, stroke = PALETTE[color]
        item["properties"]["color"] = fill
        item["properties"]["stroke"] = stroke


COUNTY_COLORS = [
    ("#e7c4a0", "#8a5a32"), ("#b7d7a8", "#3d6b3a"), ("#f0c2c0", "#8d4548"),
    ("#b9ccee", "#3d5f92"), ("#e6d48a", "#7a6420"), ("#d2c2ea", "#5c4a86"),
    ("#a9ddd2", "#2d6d64"), ("#f3c59a", "#8a5528"), ("#c5dce8", "#3e6478"),
    ("#e8c8b0", "#7a5340"), ("#cfe8b4", "#547236"), ("#f0c6dc", "#8a4570"),
    ("#d8c4a4", "#6e5434"), ("#c9e0c4", "#3f6848"), ("#e8d0c8", "#7a564c"),
    ("#d5d0ea", "#534e78"), ("#f2d2a8", "#8a6230"), ("#c4d6c8", "#3e5c48"),
]


def paint_file(path: Path, unique: bool = False) -> None:
    collection = json.loads(path.read_text())
    if unique:
        ordered = sorted(collection["features"], key=lambda item: item["properties"]["name"])
        for item, (fill, stroke) in zip(ordered, COUNTY_COLORS):
            item["properties"]["color"] = fill
            item["properties"]["stroke"] = stroke
    else:
        paint(collection["features"])
    path.write_text(json.dumps(collection, separators=(",", ":")))
    log(f"colored {path.name} ({len(collection['features'])})")


def birmingham_neighborhoods() -> list[dict]:
    query = urllib.parse.urlencode({
        "where": "1=1",
        "outFields": "NAME",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": "0.0004",
        "f": "geojson",
    })
    payload = None
    for _ in range(3):
        try:
            payload = get_json(BIRMINGHAM + "?" + query)
        except Exception as error:
            log(f"birmingham retry: {error}")
            continue
        if not payload.get("error"):
            break
        log(f"birmingham retry: {payload['error'].get('message')}")
        payload = None
    if not payload or payload.get("error"):
        raise RuntimeError("Birmingham neighborhood service did not answer")
    features = []
    for item in payload.get("features") or []:
        geom = make_valid(shape(item["geometry"]))
        geom = geom.simplify(0.0003, preserve_topology=True)
        name = (item.get("properties") or {}).get("NAME") or "Neighborhood"
        features.append(feature(
            name,
            "Birmingham",
            SOURCE["birmingham"],
            geom,
            "Official neighborhood from the City of Birmingham. The boundary is the city's, and the name is the city's.",
        ))
    log(f"birmingham neighborhoods {len(features)}")
    return features


def main() -> None:
    cities = load_cities()
    features = birmingham_neighborhoods()
    for city, name, service, where in TARGETS:
        limit = cities.get(city)
        if limit is None:
            log(f"skip {city} / {name}: no city polygon")
            continue
        endpoint = JEFF if service == "jeff" else SHELBY
        log(f"fetch {city} / {name}")
        try:
            geom = fetch_where(endpoint, where)
        except Exception as error:
            log(f"  failed: {error}")
            continue
        if geom is None:
            log("  no parcels")
            continue
        raw = polygonal(geom)
        core = polygonal(raw.intersection(limit))
        near = polygonal(raw.intersection(limit.buffer(0.003)))
        if not core.is_empty and km2(core) >= 0.05:
            clipped = core
        elif not near.is_empty and km2(near) >= 0.15:
            clipped = near
        else:
            clipped = core
        if clipped.is_empty:
            log("  outside the city limit")
            continue
        clipped = polygonal(clipped.simplify(0.00028, preserve_topology=True))
        area = km2(clipped)
        if area < 0.05:
            log(f"  too small ({area:.2f} km2)")
            continue
        features.append(feature(name, city, SOURCE[service], clipped, (
            "Prominent area named by The Move Genie. "
            "The shape is the matching county parcel neighborhood or subdivision, clipped to the city limit. "
            "It is not a surveyed neighborhood line, and it can stop short of how residents use the name."
        )))
        log(f"  kept {area:.2f} km2")

    paint(features)
    collection = {"type": "FeatureCollection", "features": features}
    dest = DATA / "neighborhoods.geojson"
    dest.write_text(json.dumps(collection, separators=(",", ":")))
    log(f"wrote {dest.name} ({len(features)} features, {dest.stat().st_size // 1024} KB)")

    paint_file(DATA / "places.geojson")
    paint_file(DATA / "counties.geojson", unique=True)


if __name__ == "__main__":
    main()
