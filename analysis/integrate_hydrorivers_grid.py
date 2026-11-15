import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from shapely.strtree import STRtree

# ==========================================
# EARTH DETECTIVE - RIVER GRID INTEGRATION
# ==========================================

GRID_PATH = Path(
    "data/processed/grids/"
    "sindh_study_window_grid_5km.geojson"
)

RIVER_PATH = Path(
    "data/processed/hydrology/"
    "hydrorivers_sindh_buffered.gpkg"
)

PUBLIC = Path("web/public/data/hydrology")
PROCESSED = Path("data/processed/hydrology")
REPORT = Path(
    "data/processed/metadata/"
    "hydrorivers_grid_integration_report.json"
)

METRIC_CRS = "EPSG:32642"

PUBLIC.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, separators=(",", ":"), allow_nan=False),
        encoding="utf-8"
    )
    tmp.replace(path)


def rounded(value, digits=4):
    if np.isfinite(value):
        return round(float(value), digits)
    return None


print("\n========== LOADING DATA ==========")

grid = gpd.read_file(GRID_PATH)

rivers = gpd.read_file(
    RIVER_PATH,
    layer="hydrorivers_sindh_buffered"
)

assert len(grid) == 12412
assert grid["cell_id"].is_unique
assert grid.geometry.is_valid.all()

assert not rivers.empty
assert rivers.geometry.notna().all()
assert rivers.geometry.is_valid.all()

print("Grid cells:", len(grid))
print("Regional river segments:", len(rivers))


# ==========================================
# PROJECT INTO METERS
# ==========================================

print("\n========== PROJECTING GEOMETRIES ==========")

grid_m = grid.to_crs(METRIC_CRS)

rivers_m = rivers.to_crs(
    METRIC_CRS
).reset_index(drop=True)

cells = grid_m.geometry.to_numpy()
lines = rivers_m.geometry.to_numpy()

N = len(cells)

order_values = pd.to_numeric(
    rivers_m["ORD_STRA"],
    errors="coerce"
).to_numpy()

print("Metric CRS:", METRIC_CRS)


# ==========================================
# BUILD SPATIAL INDEX
# ==========================================

print("\n========== BUILDING RIVER SPATIAL INDEX ==========")

tree = STRtree(lines)

# ==========================================
# NEAREST RIVER DISTANCE
# ==========================================

print("\n========== FINDING NEAREST RIVERS ==========")

# Distance from the full cell polygon to the nearest
# mapped river line. NOT center-to-center distance.

nearest_indices, nearest_distances = tree.query_nearest(
    cells,
    all_matches=False,
    return_distance=True
)

distance_m = np.full(N, np.nan, dtype=np.float64)

distance_m[nearest_indices[0]] = nearest_distances

if not np.isfinite(distance_m).all():
    raise RuntimeError(
        "Some cells have no computed nearest-river distance."
    )

if np.any(distance_m < 0):
    raise RuntimeError("Negative river distance detected.")

distance_km = distance_m / 1000.0

print("Nearest-river distances calculated:", N)
print("Minimum distance:", float(distance_km.min()), "km")
print("Maximum distance:", float(distance_km.max()), "km")


# ==========================================
# RIVER LENGTH INSIDE CELLS
# ==========================================

print("\n========== CALCULATING RIVER LENGTH ==========")

# Find all pairs of cells and river segments
# whose geometries intersect.

pairs = tree.query(
    cells,
    predicate="intersects"
)

cell_matches = pairs[0]
river_matches = pairs[1]

print("Intersecting geometry pairs:", len(cell_matches))

length_m = np.zeros(N, dtype=np.float64)
segment_count = np.zeros(N, dtype=np.int32)
max_order = np.zeros(N, dtype=np.int32)

for index, (cell_idx, river_idx) in enumerate(
    zip(cell_matches, river_matches),
    start=1
):
    cell_idx = int(cell_idx)
    river_idx = int(river_idx)

    intersection = cells[cell_idx].intersection(
        lines[river_idx]
    )

    intersection_length = float(intersection.length)

    # Ignore point-only contact with cell boundaries.
    if intersection_length <= 1e-9:
        continue

    length_m[cell_idx] += intersection_length
    segment_count[cell_idx] += 1

    order = order_values[river_idx]

    if np.isfinite(order) and order > 0:
        max_order[cell_idx] = max(
            max_order[cell_idx],
            int(order)
        )

    if index % 10000 == 0:
        print(
            f"Processed {index}/{len(cell_matches)} "
            "river-cell intersections",
            flush=True
        )

length_km = length_m / 1000.0

# A river segment inside a cell must imply zero
# distance to a mapped river.

crossed = length_m > 0

if np.any(distance_m[crossed] > 0.01):
    raise RuntimeError(
        "River length and nearest-river distance disagree."
    )


# ==========================================
# BUILD CELL RECORDS
# ==========================================

print("\n========== BUILDING HYDROLOGY MATRIX ==========")

records = []

for i, cell_id in enumerate(grid["cell_id"].astype(str)):

    has_river = bool(crossed[i])

    # The source subset extends roughly 1 degree beyond
    # the study window. Very large distances are flagged
    # because rivers beyond that buffer were not searched.

    buffer_limited = bool(distance_km[i] > 80)

    records.append({
        "cell_id": cell_id,

        "nearest_river_distance_km": rounded(
            distance_km[i]
        ),

        "river_length_km": rounded(
            length_km[i]
        ),

        "river_segment_count": int(
            segment_count[i]
        ),

        "max_strahler_order": (
            int(max_order[i])
            if max_order[i] > 0 else None
        ),

        "has_mapped_river": has_river,

        "nearest_distance_buffer_limited": buffer_limited
    })


# ==========================================
# QUALITY VALIDATION
# ==========================================

print("\n========== VALIDATING RESULT ==========")

assert len(records) == 12412

assert len({
    item["cell_id"]
    for item in records
}) == 12412

assert np.all(length_km >= 0)
assert np.all(distance_km >= 0)

cells_with_river = int(crossed.sum())
cells_without_river = N - cells_with_river

buffer_limited_cells = int(
    np.count_nonzero(distance_km > 80)
)

report = {
    "status": "complete_with_quality_flags",
    "dataset": "HydroRIVERS v1.0",
    "provider": "HydroSHEDS",
    "source_region": "Asia",
    "study_bbox": [66.0, 23.5, 71.5, 28.5],
    "source_subset_bbox": [65.0, 22.5, 72.5, 29.5],
    "metric_crs": METRIC_CRS,

    "grid_cells": N,
    "regional_river_segments": len(rivers),
    "intersecting_geometry_pairs": int(len(cell_matches)),

    "cells_with_mapped_river": cells_with_river,
    "cells_without_mapped_river": cells_without_river,

    "nearest_distance_min_km": float(
        distance_km.min()
    ),
    "nearest_distance_max_km": float(
        distance_km.max()
    ),

    "river_length_total_km": float(
        length_km.sum()
    ),

    "cells_with_buffer_limited_distance":
        buffer_limited_cells,

    "method": {
        "distance": (
            "Minimum planar distance between cell polygon "
            "and buffered HydroRIVERS line network "
            "in EPSG:32642."
        ),
        "river_length": (
            "Length of river geometry intersected "
            "with each grid cell in EPSG:32642."
        ),
        "river_order": (
            "Maximum valid Strahler order among "
            "river segments with positive length "
            "inside a cell."
        )
    },

    "limitations": [
        "HydroRIVERS is not a NASA product.",
        "River distances refer to mapped channels only.",
        "Smaller streams and canals may be absent.",
        "Nearest-river search uses a buffered regional subset.",
        "Distances greater than 80 km are flagged for review.",
        "River order is not observed flood depth.",
        "Terrain and river proximity alone cannot predict flooding."
    ]
}


# ==========================================
# EXPORT FRONTEND DATA
# ==========================================

payload = {
    "project": "Earth Detective",
    "dataset": "HydroRIVERS v1.0",
    "cell_count": N,
    "join_key": "cell_id",
    "cells": records
}

manifest = {
    "dataset": "HydroRIVERS v1.0",
    "provider": "HydroSHEDS",
    "region": "Sindh study window, Pakistan",
    "grid_cell_count": N,

    "data_url": "/data/hydrology/river_by_cell.json",

    "grid_geojson_url":
        "/data/grids/sindh_study_window_grid_5km.geojson",

    "join_key": "cell_id",
    "distance_units": "km",
    "river_length_units": "km",

    "distance_definition":
        "Shortest distance from cell polygon to mapped river line.",

    "river_order_definition":
        "Maximum intersecting Strahler order.",

    "quality_status": report["status"],
    "limitations": report["limitations"]
}

save_json(
    PUBLIC / "river_by_cell.json",
    payload
)

save_json(
    PROCESSED / "river_by_cell.json",
    payload
)

save_json(
    PUBLIC / "manifest.json",
    manifest
)

save_json(REPORT, report)


print("\n========== HYDROLOGY INTEGRATION SUMMARY ==========")

print("Grid cells:", N)
print("Regional segments:", len(rivers))
print("Cells with mapped river:", cells_with_river)
print("Cells without mapped river:", cells_without_river)

print(
    "Minimum river distance:",
    round(float(distance_km.min()), 3),
    "km"
)

print(
    "Maximum river distance:",
    round(float(distance_km.max()), 3),
    "km"
)

print(
    "Total clipped river length:",
    round(float(length_km.sum()), 3),
    "km"
)

print(
    "Cells flagged for buffer review:",
    buffer_limited_cells
)

print("Status:", report["status"])
print("Frontend:", PUBLIC / "river_by_cell.json")
print("Report:", REPORT)