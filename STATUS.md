# Status

Recorded 21 November 2026, after the cloud environment that built this map was ready to shut down. The map on `main` is the current one. Nothing in this file is still waiting on that machine.

## Merged

Both pull requests are merged. There is no open pull request.

| Pull request | What landed |
| --- | --- |
| [#1](https://github.com/CassiusCas/BRE/pull/1) | Boundary map: suburbs, counties, and school districts. |
| [#2](https://github.com/CassiusCas/BRE/pull/2) | The map that stayed. Merged at 12:37 PM ET on 21 November 2026. |

Pull request #2 was merged with the boundary map already on `main`. This page is the one that remains. County lines are visible and are not clickable. When suburbs and districts are both on, a tap opens the school district. Turn Districts off to open the suburb. School and store pins still open when tapped.

The repository is private. GitHub Pages is off, and there is no public address. Open the page from a checkout:

```bash
python3 -m http.server 8765
```

Then open http://127.0.0.1:8765

## What is saved in git

The files the page loads are committed:

- `data/places.geojson` — 156 cities, towns, and census places
- `data/counties.geojson` — 18 counties
- `data/districts.geojson` — 40 school districts, all unified
- `data/schools.json` — 431 public schools and 92 private schools
- `data/amenities.json` — 1,509 amenity places
- `data/meta.json` — center, radius, counts, and the district note
- `index.html` — the page
- `scripts/build_layers.py` — rebuilds those data files

Counts inside the 50-mile circle:

| | |
| --- | --- |
| Places | 156, including Helena, Hoover, Trussville, Homewood, Mountain Brook, and Vestavia Hills |
| Counties | Bibb, Blount, Calhoun, Chilton, Clay, Coosa, Cullman, Etowah, Fayette, Jefferson, Marshall, Perry, Shelby, St. Clair, Talladega, Tuscaloosa, Walker, Winston |
| Districts | 40 unified systems |
| Public schools | 247 elementary, 86 middle, 118 high, 72 combined or other |
| Private schools | 92, included in the level counts above |
| Amenities | 188 full groceries, 148 dollar stores, 6 warehouse clubs, 8 general stores, 32 hospitals, 24 urgent care, 118 pharmacies, 65 hardware, 14 farm supply, 15 lumber, 642 fuel, 1 propane, 103 auto parts, 145 fire stations |

Fuel, propane, auto parts, lumber, and fire stations start turned off.

## What is not in git

`raw/` and `data/raw/` are ignored. The Census, NCES, and OpenStreetMap downloads used to build the layers were only on the build machine. Shutting that machine down does not remove the committed GeoJSON and JSON. Rebuilding later re-downloads them:

```bash
python3 -m pip install -r scripts/requirements.txt
python3 scripts/build_layers.py
```

## Decisions already made

- The center is Linn Park in downtown Birmingham, 33.5207, -86.8025. The ring is 50 miles. Birmingham City Hall is about half a mile away, so the circle is effectively the same.
- Suburb shapes are the whole city or town when the place meets the circle. They are not cut at the ring.
- A county is included when the circle touches it, and the whole county is drawn.
- School districts are one overlay. All 40 systems here are unified, so one boundary covers elementary, middle, and high school. The national file does not include attendance zones inside a system.
- A circle is elementary, a square is middle, a diamond is high school, and a ring is a combined school. Blue is public and burgundy is private. A school still shows under every age group it teaches. Sixth grade stays elementary when the school stops at 6th.
- Store colors follow the brand list in project_hail_marry, plus Whole Foods, Trader Joe’s, Sprouts, Fresh Value, and The Fresh Market.
- School scores, flood layers, and parcels are not on this map.

## Still open

- Whether the 50-mile center should move to a specific address.
- Whether the edge counties should stay: Calhoun, Clay, Coosa, Cullman, Etowah, Fayette, Marshall, Perry, and Winston.
- Whether to add attendance maps that individual districts publish themselves. Those are not in the NCES file.
- Western Supermarket is not in OpenStreetMap under that name, so it is not on the map.
- Publishing. The New York map is a GitHub Pages site. This repository is private and Pages is not turned on.

## Related projects

- [new_york_map](https://github.com/CassiusCas/new_york_map) is the page this one follows.
- [project_hail_marry](https://github.com/CassiusCas/project_hail_marry) is the land-analysis pipeline. Its processed GeoPackages are not in git. This map uses the same public sources and the same amenity brand list. It is not the parcel-screening app described in that project’s plan. `land-analysis/PLAN.md` in that repository was not changed from this environment. Its phases are unchanged: the Birmingham page is a phone map, not the Phase 3 analysis site.
