import json
import re
from collections import Counter
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box
from shapely.ops import unary_union

GRID = Path(
    "data/processed/grids/sindh_study_window_grid_5km.geojson"
)
CATALOG = Path(
    "data/processed/metadata/nasadem_sindh_catalog.json"
)
PUBLIC = Path("web/public/data/terrain")
PROCESSED = Path("data/processed/terrain")
REPORT = Path(
    "data/processed/metadata/nasadem_terrain_integration_report.json"
)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(obj, separators=(",", ":"), allow_nan=False),
        encoding="utf-8"
    )
    temporary.replace(path)


def tile_geometry(tile_id):
    match = re.fullmatch(
        r"([ns])(\d{2})([ew])(\d{3})",
        tile_id.lower()
    )
    if match is None:
        raise ValueError(f"Invalid NASADEM tile: {tile_id}")

    lat = int(match.group(2))
    lon = int(match.group(4))

    if match.group(1) == "s":
        lat = -lat
    if match.group(3) == "w":
        lon = -lon

    return box(lon, lat, lon + 1, lat + 1)


print("\n========== TERRAIN COVERAGE CORRECTION ==========")

catalog = load(CATALOG)
terrain = load(PUBLIC / "terrain_by_cell.json")
manifest = load(PUBLIC / "manifest.json")
report = load(REPORT)

tiles_hgt = set(catalog["products"]["NASADEM_HGT"]["tile_ids"])
tiles_sc = set(catalog["products"]["NASADEM_SC"]["tile_ids"])

assert tiles_hgt == tiles_sc
assert len(tiles_hgt) == 39

grid = gpd.read_file(GRID)
grid_m = grid.to_crs("EPSG:6933")

records = {
    str(item["cell_id"]): item
    for item in terrain["cells"]
}

assert len(records) == len(grid) == 12412

# Exact union of the available source-tile footprints.
footprint = unary_union(
    [tile_geometry(tile) for tile in sorted(tiles_hgt)]
)

footprint_m = gpd.GeoSeries(
    [footprint],
    crs="EPSG:4326"
).to_crs("EPSG:6933").iloc[0]

statuses = Counter()
low_coverage = []
source_coverage_values = []

for index, geom in enumerate(grid_m.geometry):

    cell_id = str(grid.iloc[index]["cell_id"])
    record = records[cell_id]

    coverage = (
        100.0 * geom.intersection(footprint_m).area / geom.area
    )
    coverage = max(0.0, min(100.0, coverage))

    # Preserve the previously calculated raster-sampling estimate.
    record["sampled_coverage_pct"] = record.get(
        "sampled_coverage_pct",
        record.get("source_coverage_pct")
    )

    # Correct source coverage using the real tile geometry.
    record["source_coverage_pct"] = round(coverage, 4)
    record["tile_footprint_coverage_pct"] = round(coverage, 4)

    has_elevation = record["mean_elevation_m"] is not None
    has_slope = record["mean_slope_deg"] is not None
    water_pct = record.get("water_pct")

    if coverage < 0.01:
        status = "no_source_tile"
    elif coverage < 95:
        status = "partial_source_coverage"
    elif not has_elevation and water_pct is not None and water_pct >= 99.9:
        status = "water_only"
    elif not has_elevation or not has_slope:
        status = "missing_land_measurement"
    elif coverage < 99.9:
        status = "partial_source_coverage"
    else:
        status = "valid_land"

    record["terrain_status"] = status

    record["suitable_for_full_cell_terrain_analysis"] = (
        status == "valid_land"
    )

    statuses[status] += 1
    source_coverage_values.append(coverage)

    if coverage < 95:
        low_coverage.append(cell_id)

# Verify no geographical cell was dropped.
assert sum(statuses.values()) == 12412
assert len(terrain["cells"]) == 12412
assert max(source_coverage_values) <= 100.0

terrain["coverage_method"] = (
    "Exact projected area intersection with available NASADEM "
    "tile footprints in EPSG:6933."
)

terrain["terrain_status_definitions"] = {
    "valid_land": "Land measurements with nearly complete source-tile coverage.",
    "water_only": "Source tile available, but no land elevation measurement.",
    "no_source_tile": "No NASADEM source tile covers this cell.",
    "partial_source_coverage": "Source-tile coverage is incomplete.",
    "missing_land_measurement": "Source tile present but valid terrain measurement unavailable."
}

manifest["coverage_status"] = "documented_source_gaps"
manifest["coverage_method"] = terrain["coverage_method"]
manifest["quality_status_counts"] = dict(statuses)
manifest["limitations"].append(
    "Source tile coverage is distinct from valid land-sample coverage."
)

report["status"] = "complete_with_documented_source_gaps"
report["geometric_coverage_method"] = terrain["coverage_method"]
report["minimum_geometric_coverage_pct"] = min(source_coverage_values)
report["maximum_geometric_coverage_pct"] = max(source_coverage_values)
report["cells_below_95_percent_geometric_coverage"] = len(low_coverage)
report["quality_status_counts"] = dict(statuses)
report["source_gap_note"] = (
    "The NASADEM catalog does not include tile n23e066. "
    "Uncovered cells remain missing, not water or zero elevation."
)
report["sampling_note"] = (
    "Original raster-center sampling estimates may exceed 100%. "
    "Those estimates are preserved separately for audit purposes."
)

# Validate the complete output in memory before changing files.
assert len(low_coverage) == 240, (
    f"Expected 240 low-coverage cells; found {len(low_coverage)}"
)

save(PUBLIC / "terrain_by_cell.json", terrain)
save(PROCESSED / "terrain_by_cell.json", terrain)
save(PUBLIC / "manifest.json", manifest)
save(REPORT, report)

print("\n========== FINAL TERRAIN QUALITY SUMMARY ==========")
print("Total cells:", len(grid))
print("Available NASADEM tile pairs:", len(tiles_hgt))

for status, count in sorted(statuses.items()):
    print(f"{status}: {count}")

print("Cells below 95% coverage:", len(low_coverage))
print("Minimum geographic coverage:", min(source_coverage_values))
print("Maximum geographic coverage:", max(source_coverage_values))

print("\nOutput:", PUBLIC / "terrain_by_cell.json")
print("Report:", REPORT)
print("Status:", report["status"])