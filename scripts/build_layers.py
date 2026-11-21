#!/usr/bin/env python3
"""Build the Birmingham map layers.

The circle is 50 miles around downtown Birmingham. Polygons that touch the
circle are kept whole. School and store pins are kept only inside it.

Sources match project_hail_marry: Census TIGER places and counties, NCES EDGE
school points and district polygons, and the NCES public-school directory for
grade level. Store pins use OpenStreetMap, classified with the Hail Mary brand
list. Hail Mary's processed GeoPackages are not in git.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import requests
import shapefile
from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform, unary_union
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
DATA = ROOT / "data"

# Linn Park, downtown Birmingham. 50 miles stays inside Alabama.
LAT = 33.5207
LNG = -86.8025
MILES = 50
METERS = MILES * 1609.344

USER_AGENT = "birmingham-map/0.1 (house-shopping map)"

PLACE_URLS = [
    "https://www2.census.gov/geo/tiger/TIGER2025/PLACE/tl_2025_01_place.zip",
    "https://www2.census.gov/geo/tiger/TIGER2024/PLACE/tl_2024_01_place.zip",
]
COUNTY_URLS = [
    "https://www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip",
    "https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip",
]
PUBLIC_SCHOOL_URLS = [
    "https://nces.ed.gov/programs/edge/data/EDGE_GEOCODE_PUBLICSCH_2425.zip",
]
PRIVATE_SCHOOL_URLS = [
    "https://nces.ed.gov/programs/edge/data/EDGE_GEOCODE_PRIVATESCH_2324.zip",
]
DISTRICT_URLS = [
    "https://nces.ed.gov/programs/edge/data/EDGE_SCHOOLDISTRICT_TL25_SY2425.zip",
]
DIRECTORY_URLS = [
    "https://nces.ed.gov/ccd/Data/zip/ccd_sch_029_2425_w_1a_073025.zip",
]
PRIVATE_DIRECTORY_URLS = [
    "https://nces.ed.gov/surveys/pss/zip/pss2324_pu_csv.zip",
    "https://nces.ed.gov/surveys/pss/zip/pss2122_pu_csv.zip",
]
PBF_URLS = [
    "https://download.geofabrik.de/north-america/us/alabama/alabama-latest.osm.pbf",
]

# phrase = token boundary. exact = the folded name is one of the patterns.
# category follows land_analysis.amenities.registry, plus a few Birmingham grocers.
BRANDS = (
    ("Publix", "grocery_full", "phrase", ("publix",)),
    ("Piggly Wiggly", "grocery_full", "phrase", ("piggly wiggly",)),
    ("Walmart", "grocery_full", "phrase", ("walmart", "wal-mart")),
    ("Aldi", "grocery_full", "phrase", ("aldi",)),
    ("Kroger", "grocery_full", "phrase", ("kroger",)),
    ("Food City", "grocery_full", "phrase", ("food city",)),
    ("Ingles", "grocery_full", "phrase", ("ingles",)),
    ("Save-A-Lot", "grocery_full", "phrase", ("save-a-lot", "save a lot")),
    ("Winn-Dixie", "grocery_full", "phrase", ("winn-dixie", "winn dixie")),
    ("Food Giant", "grocery_full", "phrase", ("food giant",)),
    ("Foodland", "grocery_full", "phrase", ("foodland",)),
    ("IGA", "grocery_full", "phrase", ("iga",)),
    ("Whole Foods", "grocery_full", "phrase", ("whole foods",)),
    ("Trader Joe's", "grocery_full", "phrase", ("trader joe",)),
    ("Sprouts", "grocery_full", "phrase", ("sprouts",)),
    ("Western Supermarket", "grocery_full", "phrase", ("western supermarket",)),
    ("Fresh Value", "grocery_full", "phrase", ("fresh value",)),
    ("The Fresh Market", "grocery_full", "exact", ("the fresh market", "fresh market")),
    ("Dollar General", "grocery_small", "phrase", ("dollar general",)),
    ("Family Dollar", "grocery_small", "phrase", ("family dollar",)),
    ("Dollar Tree", "grocery_small", "phrase", ("dollar tree",)),
    ("Costco", "warehouse_club", "phrase", ("costco",)),
    ("Sam's Club", "warehouse_club", "exact", ("sam's club", "sams club")),
    ("BJ's", "warehouse_club", "phrase", ("bj's wholesale", "bjs wholesale")),
    ("Target", "general_merchandise", "exact", ("target", "supertarget")),
    ("Home Depot", "hardware_major", "phrase", ("home depot",)),
    ("Lowe's", "hardware_major", "exact", ("lowe's", "lowes", "lowe's home improvement")),
    ("Ace Hardware", "hardware_minor", "phrase", ("ace hardware",)),
    ("Harbor Freight", "hardware_minor", "phrase", ("harbor freight",)),
    ("True Value", "hardware_minor", "phrase", ("true value",)),
    ("Do it Best", "hardware_minor", "phrase", ("do it best", "doitbest")),
    ("84 Lumber", "lumber", "phrase", ("84 lumber",)),
    ("Tractor Supply", "farm_supply", "phrase", ("tractor supply",)),
    ("Rural King", "farm_supply", "phrase", ("rural king",)),
    ("CVS", "pharmacy", "phrase", ("cvs",)),
    ("Walgreens", "pharmacy", "phrase", ("walgreens", "walgreen")),
    ("AmeriGas", "propane", "phrase", ("amerigas",)),
    ("Ferrellgas", "propane", "phrase", ("ferrellgas",)),
    ("Suburban Propane", "propane", "phrase", ("suburban propane",)),
    ("O'Reilly", "auto_parts", "phrase", ("o'reilly", "oreilly")),
    ("AutoZone", "auto_parts", "phrase", ("autozone",)),
    ("NAPA", "auto_parts", "exact", ("napa auto parts", "napa")),
    ("Advance Auto Parts", "auto_parts", "phrase", ("advance auto",)),
)

URGENT_NAMES = (
    ("American Family Care", "american family care"),
    ("AFC Urgent Care", "afc urgent care"),
    ("MedHelp", "medhelp"),
    ("MinuteClinic", "minuteclinic"),
    ("MinuteClinic", "minute clinic"),
)

HOSPITAL_REJECT = (
    "clinic",
    "imaging",
    "radiology",
    "rehab",
    "hospice",
    "nursing",
    "dental",
    "animal",
    "veterinary",
    "pet",
    "pharmacy",
    "foundation",
    "auxiliary",
)

LSAD_KIND = {
    "25": "City",
    "37": "Borough",
    "43": "Town",
    "47": "Village",
    "53": "City",
    "57": "CDP",
}

OPEN_STATUS = {"1", "3", "4", "5", "8"}

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32616", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:32616", "EPSG:4326", always_xy=True)


def log(message: str) -> None:
    print(message, flush=True)


def project(geom, transformer):
    return transform(transformer.transform, geom)


def circle_geometry():
    center = project(Point(LNG, LAT), TO_UTM)
    disk = center.buffer(METERS)
    return disk, project(disk, TO_WGS)


def download(urls: list[str], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        log(f"cached {dest.name}")
        return dest
    headers = {"User-Agent": USER_AGENT}
    last = None
    for url in urls:
        log(f"get {url}")
        try:
            with requests.get(url, headers=headers, timeout=180, stream=True) as response:
                if response.status_code == 404:
                    log(f"404 {url}")
                    continue
                response.raise_for_status()
                partial = dest.with_suffix(dest.suffix + ".partial")
                with partial.open("wb") as handle:
                    for chunk in response.iter_content(1024 * 256):
                        if chunk:
                            handle.write(chunk)
                partial.replace(dest)
                log(f"saved {dest.name} ({dest.stat().st_size // 1024} KB)")
                return dest
        except requests.RequestException as error:
            last = error
            log(f"failed {url}: {error}")
    raise RuntimeError(f"Could not download {dest.name}") from last


def extract_shp(path: Path) -> Path:
    """Return a .shp path, unpacking a zip stored inside the download."""
    dest = path.with_suffix("")
    if dest.exists() and any(dest.glob("*.shp")):
        return next(dest.glob("*.shp"))
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        direct = [name for name in names if name.lower().endswith(".shp")]
        if direct:
            _unpack_sidecars(archive, direct[0], dest)
            return dest / Path(direct[0]).name
        nested = [name for name in names if name.lower().endswith(".zip")]
        if len(nested) != 1:
            raise RuntimeError(f"{path.name} has no shapefile")
        payload = archive.read(nested[0])
    with zipfile.ZipFile(io.BytesIO(payload)) as inner:
        inner_shp = [name for name in inner.namelist() if name.lower().endswith(".shp")]
        if len(inner_shp) != 1:
            raise RuntimeError(f"{path.name} inner zip has no single shapefile")
        _unpack_sidecars(inner, inner_shp[0], dest)
        return dest / Path(inner_shp[0]).name


def _unpack_sidecars(archive: zipfile.ZipFile, shp_name: str, dest: Path) -> None:
    stem = Path(shp_name).stem.lower()
    wrote = False
    for name in archive.namelist():
        if name.endswith("/") or Path(name).stem.lower() != stem:
            continue
        target = dest / Path(name).name
        target.write_bytes(archive.read(name))
        wrote = True
    if not wrote:
        raise RuntimeError(f"No shapefile parts named {stem}")


def read_records(shp_path: Path) -> tuple[list[str], list[dict]]:
    last = None
    for encoding in ("utf-8", "latin-1"):
        try:
            reader = shapefile.Reader(str(shp_path), encoding=encoding)
            fields = [field[0] for field in reader.fields[1:]]
            rows = []
            for item in reader.iterShapeRecords():
                if item.shape.shapeType == 0:
                    continue
                values = {}
                for key, value in zip(fields, item.record):
                    if isinstance(value, str):
                        value = value.strip()
                    values[key] = value
                values["__geom"] = shape(item.shape.__geo_interface__)
                rows.append(values)
            reader.close()
            return fields, rows
        except UnicodeDecodeError as error:
            last = error
    raise RuntimeError(f"Could not read {shp_path}") from last


def polygonal(geom):
    geom = make_valid(geom)
    if geom.geom_type == "GeometryCollection":
        parts = [part for part in geom.geoms if part.geom_type in ("Polygon", "MultiPolygon")]
        geom = unary_union(parts) if parts else None
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        return None
    return geom


def tidy(geom, tolerance: float):
    geom = polygonal(geom)
    if geom is None:
        return None
    geom = polygonal(geom.simplify(tolerance, preserve_topology=True))
    if geom is None:
        return None
    geom = transform(lambda x, y, z=None: (round(float(x), 5), round(float(y), 5)), geom)
    return polygonal(geom)


def feature(geom, properties: dict) -> dict:
    return {"type": "Feature", "properties": properties, "geometry": mapping(geom)}


def text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def fold(value: str) -> str:
    return text(value).casefold().replace("’", "'").replace("`", "'")


def has_phrase(folded: str, pattern: str) -> bool:
    import re

    return re.search(rf"(?<!\w){re.escape(pattern)}(?!\w)", folded) is not None


def exact_name(name: str) -> str:
    import re

    folded = fold(name)
    for _ in range(2):
        folded = re.sub(r"\s+-\s+.*$", "", folded).strip()
        folded = re.sub(r"\s+#\s*\d+$", "", folded).strip()
    return " ".join(folded.split())


def match_brand(name: str) -> tuple[str, str] | None:
    """Match a chain when the place name starts with that chain.

    A tenant inside a store, such as a pretzel shop at Walmart, keeps its own name.
    """
    import re

    exact = exact_name(name)
    primary = re.sub(r"^the\s+", "", exact)
    for canonical, category, kind, patterns in BRANDS:
        if kind == "exact":
            if exact in patterns or primary in patterns:
                return canonical, category
            continue
        if any(primary.startswith(pattern) for pattern in patterns):
            return canonical, category
    return None


def grade_label(value: str) -> str:
    token = text(value).upper()
    if token in {"KG", "K"}:
        return "K"
    if token in {"PK", "PREK", "PRE-K"}:
        return "PK"
    if token.isdigit():
        return str(int(token))
    return token


def grade_span(low: str, high: str) -> str:
    left = grade_label(low)
    right = grade_label(high)
    if not left and not right:
        return ""
    if left == right or not right:
        return left
    if not left:
        return right
    return f"{left}–{right}"


def grade_number(value: str) -> int | None:
    token = text(value).upper()
    if token in {"PK", "PREK", "PRE-K"}:
        return -1
    if token in {"KG", "K"}:
        return 0
    if token.isdigit():
        return int(token)
    return None


def bands_from_grades(low: str, high: str) -> list[str]:
    """Age groups a school actually teaches.

    In this metro a lot of elementaries run through 6th grade, so 6th grade
    counts as elementary unless the school also teaches 7th or 8th, or 6th
    grade is the whole school. High school starts at 9th.
    """
    start = grade_number(low)
    end = grade_number(high)
    if start is None or end is None or end < start:
        return []

    def has(grade: int) -> bool:
        return start <= grade <= end

    lower = any(has(grade) for grade in range(-1, 6))
    upper_middle = any(has(grade) for grade in (7, 8))
    high = any(has(grade) for grade in range(9, 13))
    if lower and not upper_middle and not high:
        return ["elementary"]
    if has(6) and not lower and not upper_middle and not high:
        return ["middle"]
    bands = []
    if lower:
        bands.append("elementary")
    if upper_middle or (has(6) and not lower):
        bands.append("middle")
    if high:
        bands.append("high")
    return bands


def shape_for(bands: list[str]) -> str:
    if len(bands) == 1:
        return bands[0]
    return "other"


def bands_for_public(level_word: str, low: str, high: str, name: str) -> list[str]:
    bands = bands_from_grades(low, high)
    # One Hoover middle school is coded 6–12. The directory still calls it middle.
    if fold(level_word) == "middle" and "high" in bands and "high school" not in fold(name):
        bands = [band for band in bands if band != "high"]
    if bands:
        return bands
    fallback = {
        "elementary": ["elementary"],
        "prekindergarten": ["elementary"],
        "middle": ["middle"],
        "high": ["high"],
        "secondary": ["high"],
        "other": ["other"],
        "not reported": ["other"],
    }
    return fallback.get(fold(level_word), [])


# PSS grade codes: 2 preschool, 3 kindergarten, 6 first grade ... 17 twelfth grade.
PSS_GRADE = {
    "2": "PK",
    "3": "KG",
    "4": "KG",
    "5": "01",
    "6": "01",
    "7": "02",
    "8": "03",
    "9": "04",
    "10": "05",
    "11": "06",
    "12": "07",
    "13": "08",
    "14": "09",
    "15": "10",
    "16": "11",
    "17": "12",
}


def kind_from_grades(low: str, high: str) -> str:
    start = grade_number(low)
    end = grade_number(high)
    if start is None or end is None:
        return "Unified"
    if end <= 8 and start < 6:
        return "Elementary"
    if start >= 6 and end <= 8:
        return "Middle"
    if start >= 9:
        return "High"
    if start >= 6 and end >= 9:
        return "Secondary"
    return "Unified"


def classify_tags(tags: dict) -> dict | None:
    """Return one amenity row, or None when the tags are out of scope."""
    if any(key.startswith(("disused", "abandoned", "was:", "demolished")) for key in tags):
        return None
    name = tags.get("name") or tags.get("brand") or ""
    if not name:
        return None
    folded = fold(name)
    brand = match_brand(name)
    amenity = tags.get("amenity", "")
    shop = tags.get("shop", "")
    healthcare = tags.get("healthcare", "")
    fuel = amenity == "fuel" or shop in {"gas", "fuel"}
    hospital = amenity == "hospital" or healthcare == "hospital"
    pharmacy = amenity == "pharmacy" or shop == "pharmacy" or healthcare == "pharmacy"
    fire = amenity == "fire_station"
    hardware = shop in {"doityourself", "hardware", "trade"}
    wholesale = shop == "wholesale"
    supermarket = shop == "supermarket"
    urgent_brand = ""
    for canonical, pattern in URGENT_NAMES:
        if has_phrase(folded, pattern):
            urgent_brand = canonical
            break
    urgent = bool(urgent_brand) or healthcare in {"urgent_care", "clinic"} and "urgent" in folded

    if hospital and any(has_phrase(folded, word) for word in HOSPITAL_REJECT):
        hospital = False
    if "physical therapy" in folded or "gift shop" in folded:
        hospital = False

    category = ""
    brand_name = ""
    if fuel and (brand is None or brand[1] not in {"pharmacy", "grocery_full"}):
        category = "fuel"
        brand_name = brand[0] if brand else ""
    elif fuel and brand and brand[1] == "grocery_full" and "fuel" in folded:
        category = "fuel"
        brand_name = brand[0]
    elif brand:
        category = brand[1]
        brand_name = brand[0]
    elif urgent:
        category = "urgent_care"
        brand_name = urgent_brand
    elif hospital:
        category = "hospital"
    elif pharmacy:
        category = "pharmacy"
    elif fire:
        category = "fire_station"
    elif supermarket:
        category = "grocery_full"
    elif wholesale:
        category = "warehouse_club"
    elif hardware:
        if shop == "trade":
            category = "lumber"
        elif shop == "doityourself":
            category = "hardware_major"
        else:
            category = "hardware_minor"
    elif "propane" in folded and not has_phrase(folded, "exchange"):
        category = "propane"
    if not category:
        return None
    number = tags.get("addr:housenumber", "")
    street = tags.get("addr:street", "")
    address = " ".join(part for part in (number, street) if part)
    return {
        "name": name,
        "brand": brand_name,
        "category": category,
        "address": address,
        "city": tags.get("addr:city", ""),
    }


def self_check() -> None:
    samples = [
        ({"name": "Publix Super Market", "shop": "supermarket"}, "Publix", "grocery_full"),
        ({"name": "Walmart Supercenter", "shop": "supermarket"}, "Walmart", "grocery_full"),
        ({"name": "Costco Wholesale", "shop": "wholesale"}, "Costco", "warehouse_club"),
        ({"name": "Sam's Club", "shop": "wholesale"}, "Sam's Club", "warehouse_club"),
        ({"name": "Target", "shop": "department_store"}, "Target", "general_merchandise"),
        ({"name": "Shell", "amenity": "fuel"}, "", "fuel"),
        ({"name": "UAB Hospital", "amenity": "hospital"}, "", "hospital"),
        ({"name": "UAB Imaging", "amenity": "hospital"}, None, None),
        ({"name": "Dollar General", "shop": "variety"}, "Dollar General", "grocery_small"),
        ({"name": "The Home Depot", "shop": "doityourself"}, "Home Depot", "hardware_major"),
        ({"name": "Western Supermarket", "shop": "supermarket"}, "Western Supermarket", "grocery_full"),
        ({"name": "CVS pharmacy", "amenity": "pharmacy"}, "CVS", "pharmacy"),
        ({"name": "Walmart Fuel Center", "amenity": "fuel"}, "Walmart", "fuel"),
        ({"name": "Auntie Anne's Gardendale Walmart", "shop": "bakery"}, None, None),
    ]
    for tags, brand, category in samples:
        got = classify_tags(tags)
        if brand is None:
            if got is not None:
                raise SystemExit(f"expected drop for {tags}, got {got}")
            continue
        if got is None or got["brand"] != brand or got["category"] != category:
            raise SystemExit(f"{tags} -> {got}, expected {brand} {category}")
    if grade_span("PK", "05") != "PK–5":
        raise SystemExit("grade span failed")
    if kind_from_grades("PK", "12") != "Unified":
        raise SystemExit("unified grades failed")
    expected_bands = {
        ("PK", "06"): ["elementary"],
        ("KG", "05"): ["elementary"],
        ("04", "06"): ["elementary"],
        ("06", "06"): ["middle"],
        ("06", "08"): ["middle"],
        ("PK", "08"): ["elementary", "middle"],
        ("09", "12"): ["high"],
        ("07", "12"): ["middle", "high"],
        ("PK", "12"): ["elementary", "middle", "high"],
    }
    for grades, bands in expected_bands.items():
        got = bands_from_grades(*grades)
        if got != bands:
            raise SystemExit(f"bands {grades} -> {got}, expected {bands}")
    log("classifier ok")


def field(row: dict, *names: str) -> str:
    for name in names:
        if name in row and text(row[name]):
            return text(row[name])
    return ""


def counties_touching(rows: list[dict], disk) -> list[dict]:
    kept = []
    for row in rows:
        if field(row, "STATEFP", "STATEFP20") not in {"01", "1"}:
            continue
        geom = polygonal(row["__geom"])
        if geom is None:
            continue
        if not project(geom, TO_UTM).intersects(disk):
            continue
        tidy_geom = tidy(geom, 0.0004)
        if tidy_geom is None:
            continue
        name = field(row, "NAME", "NAMELSAD")
        kept.append(
            {
                "name": name,
                "geom": tidy_geom,
                "utm": project(tidy_geom, TO_UTM),
            }
        )
    kept.sort(key=lambda item: item["name"])
    return kept


def county_at(point_utm, counties: list[dict]) -> str:
    point = point_utm
    for county in counties:
        if county["utm"].contains(point):
            return county["name"]
    return ""


def place_kind(row: dict) -> str:
    lsad = field(row, "LSAD")
    if lsad in LSAD_KIND:
        return LSAD_KIND[lsad]
    klass = field(row, "CLASSFP")
    if klass.startswith("U"):
        return "CDP"
    if klass.startswith("C"):
        return "City"
    return "Place"


def build_places(rows: list[dict], disk, counties: list[dict]) -> list[dict]:
    features = []
    for row in rows:
        state = field(row, "STATEFP")
        if state and state not in {"01", "1"}:
            continue
        geom = polygonal(row["__geom"])
        if geom is None or not project(geom, TO_UTM).intersects(disk):
            continue
        tidy_geom = tidy(geom, 0.00028)
        if tidy_geom is None:
            continue
        utm = project(tidy_geom, TO_UTM)
        names = []
        for county in counties:
            if county["utm"].intersects(utm):
                names.append(county["name"])
        point = tidy_geom.representative_point()
        features.append(
            feature(
                tidy_geom,
                {
                    "name": field(row, "NAME"),
                    "kind": place_kind(row),
                    "counties": ", ".join(names),
                    "area_km2": round(utm.area / 1_000_000, 1),
                    "label": [round(point.y, 5), round(point.x, 5)],
                },
            )
        )
    features.sort(key=lambda item: item["properties"]["name"])
    return features


def build_counties(counties: list[dict]) -> list[dict]:
    features = []
    for county in counties:
        point = county["geom"].representative_point()
        features.append(
            feature(
                county["geom"],
                {
                    "name": county["name"],
                    "area_km2": round(county["utm"].area / 1_000_000, 1),
                    "label": [round(point.y, 5), round(point.x, 5)],
                },
            )
        )
    return features


def district_kind(row: dict) -> str:
    for name in ("SDTYP", "SDTYPE", "DISTTYPE"):
        code = field(row, name)
        if code in {"1", "EL", "E"}:
            return "Elementary"
        if code in {"2", "SC", "S"}:
            return "Secondary"
        if code in {"7", "9", "UN", "U"}:
            return "Unified"
    unsd = field(row, "UNSDLEA")
    elsd = field(row, "ELSDLEA")
    scsd = field(row, "SCSDLEA")
    if unsd and unsd not in {"00000", "0"}:
        return "Unified"
    if elsd and not scsd:
        return "Elementary"
    if scsd and not elsd:
        return "Secondary"
    return kind_from_grades(field(row, "LOGRADE"), field(row, "HIGRADE"))


def build_districts(rows: list[dict], disk) -> tuple[list[dict], dict[str, int]]:
    features = []
    log(f"district fields: {', '.join(key for key in rows[0] if key != '__geom')}")
    for row in rows:
        state = field(row, "STATEFP", "STFIP")
        if state and state not in {"01", "1"}:
            continue
        name = field(row, "NAME")
        if "pseudo" in name.casefold() or "statewide" in name.casefold():
            continue
        # EDGE marks functioning school districts as E, not A.
        status = field(row, "FUNCSTAT")
        if status in {"I", "N", "F"}:
            continue
        geom = polygonal(row["__geom"])
        if geom is None:
            continue
        utm = project(geom, TO_UTM)
        if utm.area > 8_000_000_000:
            continue
        if not utm.intersects(disk):
            continue
        tidy_geom = tidy(geom, 0.00035)
        if tidy_geom is None:
            continue
        point = tidy_geom.representative_point()
        kind = district_kind(row)
        features.append(
            feature(
                tidy_geom,
                {
                    "name": name,
                    "kind": kind,
                    "grades": grade_span(field(row, "LOGRADE"), field(row, "HIGRADE")),
                    "area_km2": round(project(tidy_geom, TO_UTM).area / 1_000_000, 1),
                    "label": [round(point.y, 5), round(point.x, 5)],
                },
            )
        )
    features.sort(key=lambda item: item["properties"]["name"])
    counts: dict[str, int] = {}
    for item in features:
        kind = item["properties"]["kind"]
        counts[kind] = counts.get(kind, 0) + 1
    return features, counts


def zfill_id(value: str, width: int) -> str:
    token = text(value).replace(".0", "")
    if token.isdigit():
        return token.zfill(width)
    return token


def read_csv_zip(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise RuntimeError(f"{path.name} csv files: {names}")
        raw = archive.read(names[0])
    text_io = io.StringIO(raw.decode("utf-8-sig"))
    return list(csv.DictReader(text_io))


def public_directory(path: Path) -> dict[str, dict]:
    rows = read_csv_zip(path)
    if not rows:
        raise RuntimeError("school directory is empty")
    log(f"directory columns include LEVEL={ 'LEVEL' in rows[0] } SY_STATUS={'SY_STATUS' in rows[0]}")
    kept = {}
    for row in rows:
        state = text(row.get("ST") or row.get("LSTATE") or "")
        fips = text(row.get("FIPST") or "")
        if state not in {"AL"} and fips not in {"01", "1"}:
            continue
        status = text(row.get("SY_STATUS") or "")
        if status and status not in OPEN_STATUS:
            continue
        virtual = text(row.get("VIRTUAL") or "").casefold()
        if virtual in {"yes", "virtual", "1", "fullvirtual"}:
            continue
        if "virtual" in fold(row.get("SCH_NAME") or ""):
            continue
        school_id = zfill_id(row.get("NCESSCH") or "", 12)
        if not school_id:
            continue
        bands = bands_for_public(row.get("LEVEL") or "", row.get("GSLO") or "", row.get("GSHI") or "", row.get("SCH_NAME") or "")
        official = {
            "elementary": "elementary",
            "prekindergarten": "elementary",
            "middle": "middle",
            "high": "high",
            "secondary": "high",
        }.get(fold(row.get("LEVEL") or ""), "")
        if not official:
            official = shape_for(bands) if bands else "other"
        if not bands:
            bands = [official]
        grades = grade_span(row.get("GSLO") or "", row.get("GSHI") or "")
        if official == "middle" and "high" not in bands:
            end = grade_number(row.get("GSHI") or "")
            if end is not None and end > 8:
                grades = grade_span(row.get("GSLO") or "", "08")
        kept[school_id] = {
            "name": text(row.get("SCH_NAME")),
            "district": text(row.get("LEA_NAME")),
            "level": official,
            "serves": bands,
            "grades": grades,
            "address": text(row.get("LSTREET1")),
            "city": text(row.get("LCITY")),
            "charter": text(row.get("CHARTER_TEXT")).casefold() in {"yes", "1", "charter"},
        }
    log(f"public directory rows in Alabama: {len(kept)}")
    return kept


def level_from_name(name: str) -> str:
    folded = fold(name)
    flags = set()
    if any(has_phrase(folded, phrase) for phrase in ("elementary", "primary school", "grade school")):
        flags.add("elementary")
    if any(has_phrase(folded, phrase) for phrase in ("middle school", "middle", "junior high")):
        flags.add("middle")
    if any(has_phrase(folded, phrase) for phrase in ("high school", "senior high")):
        flags.add("high")
    if len(flags) == 1:
        return flags.pop()
    return "other"


def school_point(row: dict, disk) -> tuple[float, float] | None:
    lat = field(row, "LAT", "LATCOD", "Y")
    lng = field(row, "LON", "LONCOD", "X")
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except ValueError:
        return None
    if not lat_f or not lng_f:
        return None
    point = Point(lng_f, lat_f)
    if not project(point, TO_UTM).intersects(disk):
        return None
    return lat_f, lng_f


def build_public_schools(rows: list[dict], directory: dict[str, dict], disk, counties) -> list[dict]:
    if rows:
        log("public point fields: " + ", ".join(key for key in rows[0] if key != "__geom"))
    schools = []
    for row in rows:
        state = field(row, "STFIP", "STATEFP", "LSTATE")
        if state and state not in {"01", "1", "AL"}:
            continue
        located = school_point(row, disk)
        if not located:
            continue
        school_id = zfill_id(field(row, "NCESSCH"), 12)
        facts = directory.get(school_id, {})
        name = facts.get("name") or field(row, "NAME", "SCH_NAME")
        if "virtual" in fold(name):
            continue
        if facts.get("serves"):
            serves = list(facts["serves"])
            level = facts.get("level") or shape_for(serves)
            source = "directory"
        else:
            level = level_from_name(name)
            serves = [level]
            source = "name"
        point = Point(located[1], located[0])
        schools.append(
            {
                "id": school_id,
                "name": name,
                "level": level,
                "serves": serves,
                "level_source": source,
                "sector": "public",
                "charter": bool(facts.get("charter")),
                "grades": facts.get("grades") or "",
                "district": facts.get("district") or "",
                "address": facts.get("address") or field(row, "STREET", "LSTREET"),
                "city": facts.get("city") or field(row, "CITY", "LCITY"),
                "county": county_at(project(point, TO_UTM), counties),
                "lat": round(located[0], 5),
                "lng": round(located[1], 5),
            }
        )
    schools.sort(key=lambda item: item["name"])
    matched = sum(1 for school in schools if school["level_source"] == "directory")
    log(f"public schools in the circle: {len(schools)} ({matched} with a directory grade)")
    if schools and matched < len(schools) * 0.9:
        raise RuntimeError(f"Only {matched} of {len(schools)} public schools joined to the directory")
    return schools


def build_private_survey(path: Path, disk, counties) -> list[dict]:
    """Private schools from the PSS public-use file, which has grade span and coordinates."""
    rows = read_csv_zip(path)
    schools = []
    for row in rows:
        if text(row.get("PSTABB")) != "AL":
            continue
        try:
            lat = float(row.get("LATITUDE24") or "")
            lng = float(row.get("LONGITUDE24") or "")
        except ValueError:
            continue
        if not lat or not lng:
            continue
        point = Point(lng, lat)
        utm = project(point, TO_UTM)
        if not disk.intersects(utm):
            continue
        low = PSS_GRADE.get(text(row.get("LOGR2024")), "")
        high = PSS_GRADE.get(text(row.get("HIGR2024")), "")
        bands = bands_from_grades(low, high)
        code = text(row.get("LEVEL"))
        if code == "1":
            level = "elementary"
        elif code == "2":
            level = "middle" if bands == ["middle"] else "high"
        elif code == "3":
            level = "other"
        else:
            level = shape_for(bands) if bands else "other"
        if not bands:
            bands = [level]
        name = text(row.get("PINST"))
        schools.append(
            {
                "id": text(row.get("PPIN")) or name,
                "name": name,
                "level": level,
                "serves": bands,
                "level_source": "survey" if low or high else "survey-level",
                "sector": "private",
                "charter": False,
                "grades": grade_span(low, high),
                "district": "",
                "address": text(row.get("PADDRS")),
                "city": text(row.get("PCITY")).title(),
                "county": county_at(utm, counties),
                "lat": round(lat, 5),
                "lng": round(lng, 5),
            }
        )
    schools.sort(key=lambda item: item["name"])
    log(f"private schools in the circle: {len(schools)}")
    return schools


def build_private_schools(rows: list[dict], directory: dict[str, dict], disk, counties) -> list[dict]:
    if rows:
        log("private point fields: " + ", ".join(key for key in rows[0] if key != "__geom"))
    schools = []
    for row in rows:
        state = field(row, "STFIP", "STATE", "STATEFP")
        if state and state not in {"01", "1", "AL"}:
            continue
        located = school_point(row, disk)
        if not located:
            continue
        pin = zfill_id(field(row, "PPIN"), 8)
        facts = directory.get(pin, {})
        name = field(row, "NAME", "PINST")
        if facts.get("serves"):
            serves = list(facts["serves"])
            level = shape_for(serves)
            source = "directory"
        else:
            level = level_from_name(name)
            serves = [level]
            source = "name"
        point = Point(located[1], located[0])
        schools.append(
            {
                "id": pin or name,
                "name": name,
                "level": level,
                "serves": serves,
                "level_source": source,
                "sector": "private",
                "charter": False,
                "grades": facts.get("grades") or "",
                "district": "",
                "address": field(row, "STREET", "PADDR"),
                "city": field(row, "CITY", "PCITY"),
                "county": county_at(project(point, TO_UTM), counties),
                "lat": round(located[0], 5),
                "lng": round(located[1], 5),
            }
        )
    schools.sort(key=lambda item: item["name"])
    return schools


def overpass_boxes() -> list[tuple[float, float, float, float]]:
    pad = METERS / 111_320
    half_lat = MILES / 69.0
    half_lng = MILES / (69.0 * 0.832)  # cos(33.5°) ≈ 0.833
    south, north = LAT - half_lat - 0.05, LAT + half_lat + 0.05
    west, east = LNG - half_lng - 0.05, LNG + half_lng + 0.05
    mid_lat = (south + north) / 2
    mid_lng = (west + east) / 2
    overlap = 0.03
    boxes = [
        (south, west, mid_lat + overlap, mid_lng + overlap),
        (south, mid_lng - overlap, mid_lat + overlap, east),
        (mid_lat - overlap, west, north, mid_lng + overlap),
        (mid_lat - overlap, mid_lng - overlap, north, east),
    ]
    log(f"amenity window {south:.3f},{west:.3f} to {north:.3f},{east:.3f} (pad {pad:.3f})")
    return boxes


def overpass_query(box: tuple[float, float, float, float]) -> str:
    south, west, north, east = box
    bbox = f"{south},{west},{north},{east}"
    name = (
        "Publix|Walmart|Wal-Mart|Costco|Sam's Club|Sams Club|Aldi|Kroger|Piggly Wiggly|"
        "Winn-Dixie|Winn Dixie|Dollar General|Family Dollar|Dollar Tree|Home Depot|Lowe|"
        "Ace Hardware|Harbor Freight|Tractor Supply|CVS|Walgreens|AutoZone|O'Reilly|"
        "Advance Auto|NAPA|AmeriGas|Ferrellgas|True Value|Foodland|Food City|Ingles|"
        "Save-A-Lot|Save A Lot|Food Giant|Rural King|84 Lumber|Whole Foods|Trader Joe|"
        "Sprouts|Western Supermarket|Fresh Value|Fresh Market|Suburban Propane|Do it Best"
    )
    return f"""
[out:json][timeout:180];
(
  nwr["name"~"{name}",i]({bbox});
  nwr["brand"~"{name}",i]({bbox});
  nwr["shop"="supermarket"]({bbox});
  nwr["shop"="wholesale"]({bbox});
  nwr["shop"="doityourself"]({bbox});
  nwr["shop"="hardware"]({bbox});
  nwr["shop"="trade"]({bbox});
  nwr["amenity"="hospital"]({bbox});
  nwr["amenity"="pharmacy"]({bbox});
  nwr["amenity"="fuel"]({bbox});
  nwr["amenity"="fire_station"]({bbox});
  nwr["healthcare"="urgent_care"]({bbox});
);
out center tags;
"""


def interesting_tags(tags: dict) -> bool:
    amenity = tags.get("amenity", "")
    shop = tags.get("shop", "")
    healthcare = tags.get("healthcare", "")
    if amenity in {"hospital", "pharmacy", "fuel", "fire_station", "clinic"}:
        return True
    if shop in {
        "supermarket",
        "wholesale",
        "doityourself",
        "hardware",
        "trade",
        "department_store",
        "variety",
        "gas",
        "fuel",
        "car_parts",
        "pharmacy",
    }:
        return True
    if healthcare in {"hospital", "urgent_care", "pharmacy", "clinic"}:
        return True
    name = tags.get("name") or tags.get("brand") or ""
    if name and any(key in tags for key in ("shop", "amenity", "brand", "healthcare", "office")):
        if match_brand(name):
            return True
        folded = fold(name)
        if "propane" in folded or "urgent" in folded or "minute clinic" in folded or "medhelp" in folded:
            return True
    return False


def load_pbf(path: Path) -> list[dict]:
    """Read store and service points from the Alabama OpenStreetMap extract."""
    import osmium

    south, north = LAT - 0.85, LAT + 0.85
    west, east = LNG - 1.05, LNG + 1.05

    class Handler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.elements = []

        def node(self, node):
            if not node.location.valid():
                return
            lat, lng = node.location.lat, node.location.lon
            if not (south <= lat <= north and west <= lng <= east):
                return
            tags = {tag.k: tag.v for tag in node.tags}
            if not interesting_tags(tags):
                return
            self.elements.append({"type": "node", "id": node.id, "lat": lat, "lon": lng, "tags": tags})

        def way(self, way):
            tags = {tag.k: tag.v for tag in way.tags}
            if not interesting_tags(tags):
                return
            latitudes = []
            longitudes = []
            for node in way.nodes:
                if node.location.valid():
                    latitudes.append(node.location.lat)
                    longitudes.append(node.location.lon)
            if not latitudes:
                return
            lat = sum(latitudes) / len(latitudes)
            lng = sum(longitudes) / len(longitudes)
            if not (south <= lat <= north and west <= lng <= east):
                return
            self.elements.append({"type": "way", "id": way.id, "lat": lat, "lon": lng, "tags": tags})

    handler = Handler()
    handler.apply_file(str(path), locations=True)
    log(f"openstreetmap candidates: {len(handler.elements)}")
    return handler.elements


def fetch_overpass() -> list[dict]:
    cache = RAW / "overpass.json"
    if cache.exists() and cache.stat().st_size > 0:
        log(f"cached {cache.name}")
        return json.loads(cache.read_text(encoding="utf-8"))
    endpoints = (
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    )
    elements = {}
    headers = {"User-Agent": USER_AGENT}
    for box in overpass_boxes():
        query = overpass_query(box)
        payload = None
        for endpoint in endpoints:
            log(f"overpass {endpoint} {box[0]:.2f},{box[1]:.2f}")
            try:
                response = requests.post(endpoint, data={"data": query}, headers=headers, timeout=200)
                response.raise_for_status()
                payload = response.json()
                break
            except (requests.RequestException, json.JSONDecodeError) as error:
                log(f"overpass failed: {error}")
                time.sleep(3)
        if payload is None:
            raise RuntimeError("OpenStreetMap amenity query failed")
        for element in payload.get("elements", []):
            elements[(element.get("type"), element.get("id"))] = element
        time.sleep(1)
    found = list(elements.values())
    log(f"overpass elements: {len(found)}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(found), encoding="utf-8")
    return found


def element_latlng(element: dict) -> tuple[float, float] | None:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def dedupe_amenities(rows: list[dict]) -> list[dict]:
    """Keep one row per category and brand (or name) inside 150 meters."""
    cell = 150
    occupied: dict[tuple, list[tuple[float, float]]] = {}
    kept = []
    rows = sorted(rows, key=lambda row: (0 if row["brand"] else 1, 0 if row["address"] else 1, row["name"]))
    for row in rows:
        point = project(Point(row["lng"], row["lat"]), TO_UTM)
        key = (row["category"], row["brand"] or fold(row["name"]))
        cx, cy = int(point.x // cell), int(point.y // cell)
        near = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other_x, other_y in occupied.get((key, cx + dx, cy + dy), []):
                    if (point.x - other_x) ** 2 + (point.y - other_y) ** 2 <= cell ** 2:
                        near = True
                        break
        if near:
            continue
        occupied.setdefault((key, cx, cy), []).append((point.x, point.y))
        kept.append(row)
    return kept


def build_amenities(elements: list[dict], disk, counties: list[dict]) -> list[dict]:
    rows = []
    for element in elements:
        located = element_latlng(element)
        if not located:
            continue
        point = Point(located[1], located[0])
        utm = project(point, TO_UTM)
        if not disk.intersects(utm):
            continue
        tags = element.get("tags") or {}
        classified = classify_tags(tags)
        if classified is None:
            continue
        classified.update(
            {
                "lat": round(located[0], 5),
                "lng": round(located[1], 5),
                "county": county_at(utm, counties),
            }
        )
        if not classified["city"]:
            classified["city"] = classified["county"]
        rows.append(classified)
    rows = dedupe_amenities(rows)
    rows.sort(key=lambda row: (row["category"], row["brand"], row["name"]))
    return rows


def district_note(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    unified = counts.get("Unified", 0)
    if total and unified == total:
        return (
            f"All {total} districts in this circle are unified systems. "
            "One boundary is the public school system for that address, and it covers elementary, middle, and high school. "
            "Separate attendance zones inside a system are drawn by the district and are not in the national map."
        )
    parts = ", ".join(f"{count} {kind.lower()}" for kind, count in sorted(counts.items()))
    return (
        f"{total} districts meet this circle ({parts}). "
        "A unified district is the public system for every grade. "
        "Elementary or secondary districts are labeled when you tap them. "
        "Attendance zones inside a system are not in the national map."
    )


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    log(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    self_check()
    disk, _ring = circle_geometry()
    place_shp = extract_shp(download(PLACE_URLS, RAW / "places.zip"))
    county_shp = extract_shp(download(COUNTY_URLS, RAW / "counties.zip"))
    _place_fields, place_rows = read_records(place_shp)
    _county_fields, county_rows = read_records(county_shp)
    log(f"place fields: {', '.join(_place_fields)}")
    counties = counties_touching(county_rows, disk)
    place_features = build_places(place_rows, disk, counties)
    county_features = build_counties(counties)

    district_shp = extract_shp(download(DISTRICT_URLS, RAW / "districts.zip"))
    _district_fields, district_rows = read_records(district_shp)
    district_features, kind_counts = build_districts(district_rows, disk)

    directory = public_directory(download(DIRECTORY_URLS, RAW / "ccd_directory.zip"))
    public_shp = extract_shp(download(PUBLIC_SCHOOL_URLS, RAW / "public_schools.zip"))
    _public_fields, public_rows = read_records(public_shp)
    public_schools = build_public_schools(public_rows, directory, disk, counties)
    try:
        private_schools = build_private_survey(download(PRIVATE_DIRECTORY_URLS, RAW / "pss.zip"), disk, counties)
    except RuntimeError as error:
        log(str(error))
        private_shp = extract_shp(download(PRIVATE_SCHOOL_URLS, RAW / "private_schools.zip"))
        _private_fields, private_rows = read_records(private_shp)
        private_schools = build_private_schools(private_rows, {}, disk, counties)
    schools = public_schools + private_schools

    try:
        amenity_elements = load_pbf(download(PBF_URLS, RAW / "alabama.osm.pbf"))
    except (RuntimeError, OSError) as error:
        log(f"OpenStreetMap extract failed ({error}); trying the Overpass service")
        amenity_elements = fetch_overpass()
    amenities = build_amenities(amenity_elements, disk, counties)

    write_json(DATA / "places.geojson", {"type": "FeatureCollection", "features": place_features})
    write_json(DATA / "counties.geojson", {"type": "FeatureCollection", "features": county_features})
    write_json(DATA / "districts.geojson", {"type": "FeatureCollection", "features": district_features})
    write_json(DATA / "schools.json", schools)
    write_json(DATA / "amenities.json", amenities)

    place_names = {item["properties"]["name"] for item in place_features}
    county_names = {item["properties"]["name"] for item in county_features}
    for name in ("Birmingham", "Hoover", "Helena", "Trussville", "Homewood", "Mountain Brook", "Vestavia Hills"):
        require(name in place_names, f"missing suburb {name}")
    for name in ("Jefferson", "Shelby", "St. Clair", "Blount"):
        require(name in county_names, f"missing county {name}")
    served = {band for school in public_schools for band in school["serves"]}
    require({"elementary", "middle", "high"} <= served, f"public levels missing: {served}")
    require(len(public_schools) > 80, "too few public schools")
    require(len(private_schools) > 10, "too few private schools")
    brands = {row["brand"] for row in amenities}
    for brand in ("Publix", "Walmart", "Costco"):
        require(brand in brands, f"missing {brand}")

    counts = {}
    for row in amenities:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    meta = {
        "center": [LAT, LNG],
        "miles": MILES,
        "place": "Downtown Birmingham",
        "places": len(place_features),
        "counties": sorted(county_names),
        "districts": len(district_features),
        "district_kinds": kind_counts,
        "district_note": district_note(kind_counts),
        "schools": {
            "public": len(public_schools),
            "private": len(private_schools),
            "by_level": {
                level: sum(1 for school in schools if school["level"] == level)
                for level in ("elementary", "middle", "high", "other")
            },
        },
        "amenities": counts,
        "sources": {
            "places": "US Census TIGER places, Alabama",
            "counties": "US Census TIGER counties",
            "districts": "NCES EDGE school district boundaries, 2024-25",
            "schools": "NCES EDGE public school locations 2024-25, private school locations 2023-24, CCD directory",
            "amenities": "OpenStreetMap, classified with the project_hail_marry brand list",
        },
    }
    (DATA / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log(json.dumps(meta, indent=2))


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as error:
        sys.exit(f"download failed: {error}")
