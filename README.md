# Birmingham

A phone-friendly map for house shopping around Birmingham, Alabama. It covers downtown and the surrounding 50 miles: suburb limits, counties, public school districts, school locations, and everyday amenities.

The current map is on `main`. [STATUS.md](STATUS.md) is the record of what was merged on 21 November 2026, what is saved in git, and what is still open. The page is not published. There is no public web address yet.

The page is one HTML file plus the data files in `data/`. The street map underneath loads from the internet. Pins and boundaries are saved in this project, the same way [new_york_map](https://github.com/CassiusCas/new_york_map) keeps its places on the page.

## Open it locally

From this folder:

```bash
python3 -m http.server 8765
```

Then open http://127.0.0.1:8765

The title zooms back out to the 50-mile ring. **Near me** uses the browser’s location. Search keeps every word: `hoover elementary`, `private high`, `publix`, `shelby`.

## Layers

- **Suburbs** are Census cities, towns, and census-designated places that meet the circle. That includes Helena, Hoover, Trussville, Homewood, Mountain Brook, Vestavia Hills, and the smaller places around them. Touching places use different colors, and the name is drawn in that color. Names appear as you zoom in.
- **Counties** are a separate overlay. A county is included when the 50-mile circle touches it, and the whole county is drawn in its own color. The lines are visible and are not clickable, so a tap still lands on the suburb or the school district underneath. Search or the list still opens a county by name.
- **Neighborhoods** start off. Turn the layer on to see Birmingham’s official neighborhoods, plus prominent areas in Hoover, Helena, Vestavia Hills, Homewood, Mountain Brook, Trussville, Irondale, Gardendale, Leeds, and Pelham. Those names come from The Move Genie. Birmingham’s shapes are the city GIS boundaries. A suburb shape is the county parcel area that uses that name, clipped to the city, so it can be smaller than the way residents use the name. English Village and Cahaba Village are only a few acres in the county file, so they are not drawn. A tap opens the neighborhood while the layer is on.
- **Districts** are the public school system boundaries from NCES. In this circle those systems are unified: one boundary covers elementary, middle, and high school. Alabama does not publish separate attendance zones for each grade in the national file. Those zones are drawn by each district. The school pins are the grade-level view. When Neighborhoods are off and Districts are on, a tap opens the district. Turn Districts off to open the suburb.
- **Schools** are NCES locations. A circle is elementary, a square is middle, and a diamond is high school. The ring is a combined school. A school still shows under every age group it teaches, so a 7–12 high school stays a diamond and also appears when Middle is on. Around Birmingham, 6th grade stays with elementary when the school stops at 6th. Blue is public and burgundy is private. The chips under the search box turn levels and public or private on and off.
- **Amenities** use the store list from project_hail_marry. Publix, Walmart, Costco, and the other named chains each have their own color and letters. Hospitals, pharmacies, hardware stores, and the rest share a symbol per category. Fuel, propane, auto parts, lumber, and fire stations start off so they do not cover the map.

## Where the data comes from

| Layer | Source |
| --- | --- |
| Suburbs and counties | US Census TIGER 2025 |
| Birmingham neighborhoods | City of Birmingham GIS |
| Suburb neighborhoods | Jefferson County and Shelby County parcel maps, for areas named on The Move Genie |
| School districts | NCES EDGE school district boundaries, 2024–25 |
| Public schools | NCES EDGE locations, 2024–25, with grade level from the CCD directory |
| Private schools | NCES EDGE locations, 2023–24 |
| Amenities | OpenStreetMap, classified with the Hail Mary brand list |

Hail Mary’s processed files are not in that repository, so this map rebuilds the same public layers for the 50-mile circle. A few Birmingham grocers that are not in the Hail Mary brand table are included: Western Supermarket, Fresh Value, Whole Foods, Trader Joe’s, Sprouts, and The Fresh Market. School scores and flood layers are not on this map. Parcel lines are not drawn; a few suburb neighborhood shapes are dissolved from them.

The center is Linn Park in downtown Birmingham. Rebuild the files with:

```bash
python3 -m pip install -r scripts/requirements.txt
python3 scripts/build_layers.py
python3 scripts/build_neighborhoods.py
```

Downloads are cached in `raw/`, which is not committed.

Street map data is © OpenStreetMap contributors, via [OpenFreeMap](https://openfreemap.org).
