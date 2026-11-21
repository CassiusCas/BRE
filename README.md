# Birmingham

A phone map of Birmingham and the 50 miles around it, for a first look while house shopping. It follows the same shape as the New York map: one page, a street map underneath, and overlays you turn on and off. There is no server to run.

Open the published page in Safari or Chrome, pinch to zoom, and tap an area. The street names load when the phone is online.

## What you can turn on

- **Suburbs** draws city limits and census-designated places inside the circle: Helena, Hoover, Trussville, Homewood, Mountain Brook, and the rest. A place that only partly falls inside the 50 miles is cut at the circle.
- **Counties** draws the counties that meet that circle, including Jefferson and Shelby.
- **Districts** draws public school district boundaries for the same area, with the grade span from the district file (for example KG–12).

The three toggles are separate. The phone remembers which ones you left on. Search matches the name of whatever is turned on. **List** opens that same set. **Near me** uses the phone’s location. Tap the title to zoom back out to the 50-mile circle.

County lines are visible and are not clickable, so a tap still lands on the suburb or the school district underneath. When both of those are on, the tap opens the school district. Turn Districts off to open the suburb instead.

## Where the lines come from

These are the boundary layers from the land-analysis work, clipped to 50 miles of Birmingham City Hall and simplified so the page stays small.

- Places and counties: U.S. Census TIGER/Line 2025.
- School districts: NCES EDGE composite district polygons, 2024–25.
- Streets: [OpenFreeMap](https://openfreemap.org). Map data is © OpenStreetMap contributors.

`scripts/build_layers.py` rebuilds `data/suburbs.geojson`, `data/counties.geojson`, `data/districts.geojson`, and `data/radius.geojson`. The raw downloads stay out of git.

School test scores, spending, flood, and parcels from that project are not on this map. This page is the boundary view you can open on a phone.
