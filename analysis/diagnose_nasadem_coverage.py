import json
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union

GRID = Path(
    "data/processed/grids/sindh_study_window_grid_5km.geojson"
)

TERRAIN = Path(
    "web/public/data/terrain/terrain_by_cell.json"
)

CATALOG = Path(
    "data/processed/metadata/nasadem_sindh_catalog.json"
)

OUTPUT = Path(
    "data/processed/metadata/nasadem_coverage_diagnostic.json"
)


def tile_box(tile):
    m = re.fullmatch(
        r"([ns])(\d{2})([ew])(\d{3})",
        tile.lower()
    )
    if not m:
        raise ValueError(f"Unexpected tile ID: {tile}")

    lat = int(m.group(2))
    lon = int(m.group(4))

    if m.group(1) == "s":
        lat = -lat
    if m.group(3) == "w":
        lon = -lon

    return box(lon, lat, lon + 1, lat + 1)


with CATALOG.open(encoding="utf-8") as f:
    catalog = json.load(f)

with TERRAIN.open(encoding="utf-8") as f:
    terrain = json.load(f)

grid = gpd.read_file(GRID)
records = terrain["cells"]

assert len(grid) == 12412
assert len(records) == len(grid)

tile_ids = set(
    catalog["products"]["NASADEM_HGT"]["tile_ids"]
)

# Detect missing tiles in the rectangular study area.
expected_tile_ids = {
    f"n{lat:02d}e{lon:03d}"
    for lat in range(23, 29)
    for lon in range(66, 72)
}

missing_tile_ids = sorted(expected_tile_ids - tile_ids)

footprint_4326 = unary_union([
    tile_box(t) for t in sorted(tile_ids)
])

footprint_6933 = gpd.GeoSeries(
    [footprint_4326],
    crs="EPSG:4326"
).to_crs("EPSG:6933").iloc[0]

grid_6933 = grid.to_crs("EPSG:6933")

record_by_id = {
    str(record["cell_id"]): record
    for record in records
}

assert len(record_by_id) == len(records)

low_coverage = []
unexpected_low = []
no_land_elevation = []
zero_coverage = []

for i, geom in enumerate(grid_6933.geometry):

    cell_id = str(grid.iloc[i]["cell_id"])
    record = record_by_id[cell_id]

    reported = record.get("source_coverage_pct")
    reported = float(reported) if reported is not None else 0.0

    expected = (
        100.0 * geom.intersection(footprint_6933).area / geom.area
    )

    center = grid.geometry.iloc[i].centroid

    item = {
        "cell_id": cell_id,
        "longitude": round(float(center.x), 5),
        "latitude": round(float(center.y), 5),
        "reported_coverage_pct": reported,
        "tile_footprint_coverage_pct": round(float(expected), 3),
        "land_pct": record.get("land_pct"),
        "water_pct": record.get("water_pct"),
        "mean_elevation_m": record.get("mean_elevation_m")
    }

    if reported < 95:
        low_coverage.append(item)

        if expected >= 99:
            unexpected_low.append(item)

    if reported == 0:
        zero_coverage.append(item)

    if record.get("mean_elevation_m") is None:
        no_land_elevation.append(item)


low_coverage.sort(
    key=lambda x: x["reported_coverage_pct"]
)

expected_missing = sum(
    x["tile_footprint_coverage_pct"] < 95
    for x in low_coverage
)

water_only = sum(
    x["water_pct"] is not None
    and x["water_pct"] >= 99.9
    for x in no_land_elevation
)

land_but_no_elevation = sum(
    x["land_pct"] is not None
    and x["land_pct"] > 0
    for x in no_land_elevation
)

summary = {
    "total_cells": len(grid),
    "downloaded_tile_count": len(tile_ids),
    "missing_study_window_tiles": missing_tile_ids,
    "cells_below_95_pct": len(low_coverage),
    "low_cells_with_tile_footprint_below_95_pct": expected_missing,
    "low_cells_with_tile_footprint_at_least_99_pct":
        len(unexpected_low),
    "zero_coverage_cells": len(zero_coverage),
    "cells_without_land_elevation": len(no_land_elevation),
    "water_only_cells_without_land_elevation": water_only,
    "cells_with_land_but_no_elevation":
        land_but_no_elevation
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

OUTPUT.write_text(
    json.dumps(
        {
            "summary": summary,
            "low_coverage_cells": low_coverage,
            "unexpected_low_coverage_cells": unexpected_low
        },
        indent=2
    ),
    encoding="utf-8"
)

print("\n========== NASADEM COVERAGE DIAGNOSTIC ==========")

for key, value in summary.items():
    print(f"{key}: {value}")

print("\n========== WORST 15 CELLS ==========")

for item in low_coverage[:15]:
    print(
        f"Cell {item['cell_id']}: "
        f"actual={item['reported_coverage_pct']:.2f}%, "
        f"tile_footprint={item['tile_footprint_coverage_pct']:.2f}%, "
        f"location=({item['latitude']}, {item['longitude']})"
    )

print("\nReport:", OUTPUT)
print("Diagnostic complete. No terrain data was modified.")