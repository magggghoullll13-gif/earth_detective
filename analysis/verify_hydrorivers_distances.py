import json
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import box
from shapely.strtree import STRtree

# EARTH DETECTIVE - RIVER DISTANCE VERIFICATION

GRID = Path(
    "data/processed/grids/"
    "sindh_study_window_grid_5km.geojson"
)
ARCHIVE = Path(
    "data/raw/hydrology/hydrorivers/"
    "HydroRIVERS_v10_as_shp.zip"
)
DATA = Path(
    "web/public/data/hydrology/river_by_cell.json"
)
PROCESSED = Path(
    "data/processed/hydrology/river_by_cell.json"
)
MANIFEST = Path(
    "web/public/data/hydrology/manifest.json"
)
REPORT = Path(
    "data/processed/metadata/"
    "hydrorivers_grid_integration_report.json"
)
AUDIT = Path(
    "data/processed/metadata/"
    "hydrorivers_distance_verification.json"
)

# Expanded by approximately 3 degrees on every side.
SEARCH_BBOX = (63.0, 20.5, 74.5, 31.5)
CRS = "EPSG:32642"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(
            value,
            separators=(",", ":"),
            allow_nan=False
        ),
        encoding="utf-8"
    )
    temp.replace(path)

print("\n========== LOADING EXISTING DATA ==========")

grid = gpd.read_file(GRID)
payload = load(DATA)
manifest = load(MANIFEST)
report = load(REPORT)

assert len(grid) == 12412
assert len(payload["cells"]) == 12412
assert grid["cell_id"].is_unique

records_by_id = {
    str(record["cell_id"]): record
    for record in payload["cells"]
}
assert len(records_by_id) == 12412

grid_m = grid.to_crs(CRS)
cells = grid_m.geometry.to_numpy()
cell_ids = grid["cell_id"].astype(str).tolist()

old_distances = np.array([
    float(records_by_id[c]["nearest_river_distance_km"])
    for c in cell_ids
])

print("Grid cells:", len(cells))
print("Previous maximum distance:", old_distances.max(), "km")

print("\n========== READING EXPANDED RIVER REGION ==========")

uri = (
    "zip://" + ARCHIVE.resolve().as_posix()
    + "!HydroRIVERS_v10_as_shp/"
    + "HydroRIVERS_v10_as.shp"
)

rivers = gpd.read_file(
    uri,
    bbox=SEARCH_BBOX,
    engine="pyogrio"
)

assert rivers.crs.to_epsg() == 4326

rivers = rivers.loc[
    rivers.geometry.notna()
    & ~rivers.geometry.is_empty
].copy()

# Clip all river geometries to the expanded region.
# This lets us bound the nearest-distance uncertainty.

search_polygon = box(*SEARCH_BBOX)

rivers["geometry"] = rivers.geometry.intersection(
    search_polygon
)

rivers = rivers.loc[
    rivers.geometry.geom_type.isin([
        "LineString", "MultiLineString"
    ])
    & ~rivers.geometry.is_empty
].copy()

assert not rivers.empty

print("Expanded river segments:", len(rivers))

rivers_m = rivers.to_crs(CRS)
lines = rivers_m.geometry.to_numpy()

print("\n========== RECALCULATING DISTANCES ==========")

tree = STRtree(lines)

pairs, distances_m = tree.query_nearest(
    cells,
    all_matches=False,
    return_distance=True
)

new_distances_m = np.full(
    len(cells), np.nan, dtype=np.float64
)
new_distances_m[pairs[0]] = distances_m

assert np.isfinite(new_distances_m).all()
assert (new_distances_m >= 0).all()

new_distances_km = new_distances_m / 1000.0

# Because the new network contains the old buffered
# network, new nearest distances should not increase
# materially. Allow tolerance for geometric precision
# and rounding from the old JSON values.

increase = new_distances_km - old_distances

if np.any(increase > 0.02):
    raise RuntimeError(
        "Unexpected increase in nearest-river distance. "
        "Review the geometry before replacing data."
    )

print(
    "Cells with distance reduction > 1 meter:",
    int(np.count_nonzero(
        old_distances - new_distances_km > 0.001
    ))
)

print(
    "Old maximum:", round(float(old_distances.max()), 3),
    "km"
)
print(
    "New maximum:", round(float(new_distances_km.max()), 3),
    "km"
)

print("\n========== VERIFYING SEARCH BOUNDARY ==========")

# Densify the geographic search boundary before
# projection, to follow its edges more accurately.

boundary_4326 = search_polygon.segmentize(0.05)

boundary_m = gpd.GeoSeries(
    [boundary_4326],
    crs="EPSG:4326"
).to_crs(CRS).iloc[0].boundary

distance_to_search_edge_m = np.array([
    geom.distance(boundary_m)
    for geom in cells
])

# If the nearest river is closer than every part
# of the search boundary, no river entirely outside
# the search region can be a nearer candidate.

certified = (
    new_distances_m + 1.0
    < distance_to_search_edge_m
)

uncertain_count = int(np.count_nonzero(~certified))

print("Verified distance cells:", int(certified.sum()))
print("Still boundary-limited:", uncertain_count)
print(
    "Minimum distance to search boundary:",
    round(
        float(distance_to_search_edge_m.min()) / 1000,
        3
    ),
    "km"
)

print("\n========== UPDATING HYDROLOGY DATA ==========")

changed_count = 0

audit_changes = []

for i, cell_id in enumerate(cell_ids):
    record = records_by_id[cell_id]

    old = float(record["nearest_river_distance_km"])
    new = round(float(new_distances_km[i]), 4)

    if abs(old - new) > 0.001:
        changed_count += 1
        audit_changes.append({
            "cell_id": cell_id,
            "old_distance_km": old,
            "new_distance_km": new
        })

    record["nearest_river_distance_km"] = new
    record["nearest_distance_buffer_limited"] = (
        not bool(certified[i])
    )

    record["nearest_distance_verified"] = (
        bool(certified[i])
    )

    # Other values, including river length,
    # segment counts and orders, are unchanged.

assert len(payload["cells"]) == 12412

report["previous_nearest_river_max_km"] = report[
    "nearest_distance_max_km"
]
report["nearest_distance_max_km"] = float(
    new_distances_km.max()
)
report["nearest_distance_min_km"] = float(
    new_distances_km.min()
)
report["nearest_distance_source_subset_bbox"] = list(
    SEARCH_BBOX
)
report["expanded_nearest_river_segments"] = len(rivers)
report["verified_nearest_distance_cells"] = int(
    certified.sum()
)
report["cells_with_buffer_limited_distance"] = uncertain_count
report["distance_values_changed_gt_1m"] = changed_count

report["status"] = (
    "validated_with_source_limitations"
    if uncertain_count == 0
    else "requires_further_distance_review"
)

report["method"]["distance"] = (
    "Minimum cell-polygon-to-river-line distance "
    "in EPSG:32642 using an expanded regional "
    "network. Completeness checked against distance "
    "to the search region boundary."
)

report["limitations"] = [
    note for note in report.get("limitations", [])
    if "80 km" not in note
]

report["limitations"].append(
    "River proximity refers only to channels "
    "represented in HydroRIVERS."
)

manifest["quality_status"] = report["status"]
manifest["nearest_distance_source_bbox"] = list(
    SEARCH_BBOX
)
manifest["verified_nearest_distance_cells"] = int(
    certified.sum()
)

audit = {
    "status": report["status"],
    "old_max_km": float(old_distances.max()),
    "new_max_km": float(new_distances_km.max()),
    "verified_cells": int(certified.sum()),
    "uncertain_cells": uncertain_count,
    "changed_cells_gt_1m": changed_count,
    "changed_distances": audit_changes
}

# Write only after all calculations and checks pass.
save(DATA, payload)
save(PROCESSED, payload)
save(MANIFEST, manifest)
save(REPORT, report)
save(AUDIT, audit)

print("\n========== RIVER DISTANCE VERIFICATION SUMMARY ==========")
print("Grid cells:", len(cells))
print("Expanded river segments:", len(rivers))
print("Old maximum distance:", round(float(old_distances.max()), 3), "km")
print("New maximum distance:", round(float(new_distances_km.max()), 3), "km")
print("Distances changed > 1m:", changed_count)
print("Verified distance cells:", int(certified.sum()))
print("Remaining uncertain cells:", uncertain_count)
print("Status:", report["status"])
print("Report:", AUDIT)