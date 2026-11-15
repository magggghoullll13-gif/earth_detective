import json
import re
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np

from affine import Affine
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import box


# ==========================================
# EARTH DETECTIVE - TERRAIN INTEGRATION
# ==========================================

ROOT = Path("data/raw/pakistan/nasadem")
CATALOG = Path(
    "data/processed/metadata/nasadem_sindh_catalog.json"
)
GRID_PATH = Path(
    "data/processed/grids/sindh_study_window_grid_5km.geojson"
)

PUBLIC = Path("web/public/data/terrain")
PROCESSED = Path("data/processed/terrain")
REPORT = Path(
    "data/processed/metadata/nasadem_terrain_integration_report.json"
)

SIZE = 3601
USED_SIZE = 3600
STEP = 1.0 / 3600.0
STRIPE = 256

PUBLIC.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)


def read_zip(path, filename, dtype):
    with zipfile.ZipFile(path) as archive:
        data = archive.read(filename)

    values = np.frombuffer(data, dtype=dtype)

    if values.size != SIZE * SIZE:
        raise ValueError(
            f"Invalid raster dimensions: {filename}"
        )

    return values.reshape(SIZE, SIZE)[:-1, :-1]


def coordinates(tile):
    match = re.fullmatch(
        r"([ns])(\d{2})([ew])(\d{3})",
        tile.lower()
    )

    if not match:
        raise ValueError(f"Invalid tile ID: {tile}")

    latitude = int(match.group(2))
    longitude = int(match.group(4))

    if match.group(1) == "s":
        latitude = -latitude

    if match.group(3) == "w":
        longitude = -longitude

    return longitude, latitude


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    temp = path.with_suffix(path.suffix + ".tmp")

    temp.write_text(
        json.dumps(data, separators=(",", ":"), allow_nan=False),
        encoding="utf-8"
    )

    temp.replace(path)


def numeric(value, digits=3):
    if np.isfinite(value):
        return round(float(value), digits)
    return None


print("\n========== LOADING UNIVERSAL GRID ==========")

grid = gpd.read_file(GRID_PATH)

assert len(grid) == 12412
assert grid.crs.to_epsg() == 4326
assert grid["cell_id"].is_unique
assert grid.geometry.is_valid.all()

cell_ids = grid["cell_id"].astype(str).tolist()
N = len(grid)

grid_area = grid.to_crs("EPSG:6933").geometry.area.to_numpy()

tree = grid.sindex

transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:6933",
    always_xy=True
)

with CATALOG.open(encoding="utf-8") as file:
    catalog = json.load(file)

hgt_tiles = set(
    catalog["products"]["NASADEM_HGT"]["tile_ids"]
)
sc_tiles = set(
    catalog["products"]["NASADEM_SC"]["tile_ids"]
)

assert hgt_tiles == sc_tiles
assert len(hgt_tiles) == 39

tiles = sorted(hgt_tiles)

# Index zero is reserved for samples outside the grid.

covered_area = np.zeros(N + 1)
classified_area = np.zeros(N + 1)
land_area = np.zeros(N + 1)
water_area = np.zeros(N + 1)

elev_area = np.zeros(N + 1)
elev_sum = np.zeros(N + 1)

slope_area = np.zeros(N + 1)
slope_sum = np.zeros(N + 1)

steep5_area = np.zeros(N + 1)
steep15_area = np.zeros(N + 1)

elev_min = np.full(N + 1, np.inf)
elev_max = np.full(N + 1, -np.inf)
slope_max = np.full(N + 1, -np.inf)

mask_mismatches = 0
invalid_slope_samples = 0
invalid_water_samples = 0

print("Cells:", N)
print("Terrain tile pairs:", len(tiles))


# ==========================================
# PROCESS TILE BY TILE
# ==========================================

print("\n========== PROCESSING NASADEM TILES ==========")

for tile_number, tile in enumerate(tiles, start=1):

    west, south = coordinates(tile)
    north = south + 1

    hgt_path = (
        ROOT / "NASADEM_HGT"
        / f"NASADEM_HGT_{tile}.zip"
    )

    sc_path = (
        ROOT / "NASADEM_SC"
        / f"NASADEM_SC_{tile}.zip"
    )

    if not hgt_path.exists() or not sc_path.exists():
        raise FileNotFoundError(f"Missing terrain tile: {tile}")

    elevation = read_zip(
        hgt_path, f"{tile}.hgt", ">i2"
    )

    water_hgt = read_zip(
        hgt_path, f"{tile}.swb", "u1"
    )

    slope_raw = read_zip(
        sc_path, f"{tile}.slope", ">u2"
    )

    water_sc = read_zip(
        sc_path, f"{tile}.swb", "u1"
    )

    mask_mismatches += int(
        np.count_nonzero(water_hgt != water_sc)
    )

    # Original NASADEM: 3601 x 3601 geographic posts.
    # Drop southern and eastern edge posts so shared
    # posts between neighboring tiles count only once.

    transform = Affine(
        STEP, 0, west - STEP / 2,
        0, -STEP, north + STEP / 2
    )

    tile_box = box(
        west, south, west + 1, north
    )

    candidates = tree.query(
        tile_box,
        predicate="intersects"
    )

    shapes = [
        (
            grid.geometry.iloc[int(i)],
            int(i) + 1
        )
        for i in candidates
    ]

    if not shapes:
        print(f"{tile_number:02d}/39 {tile}: no grid overlap")
        continue

    # A pixel center receives the corresponding grid ID.

    cell_raster = rasterize(
        shapes,
        out_shape=(USED_SIZE, USED_SIZE),
        transform=transform,
        fill=0,
        dtype="int32",
        all_touched=False
    )

    # Projected area of each geographic raster sample.
    # Pixel area varies with latitude.

    lat_upper = (
        north + STEP / 2
        - np.arange(USED_SIZE) * STEP
    )
    lat_lower = lat_upper - STEP

    x0, _ = transformer.transform(
        west - STEP / 2, north
    )
    x1, _ = transformer.transform(
        west + STEP / 2, north
    )

    _, projected_upper = transformer.transform(
        np.full(USED_SIZE, west),
        lat_upper
    )

    _, projected_lower = transformer.transform(
        np.full(USED_SIZE, west),
        lat_lower
    )

    row_areas = (
        abs(x1 - x0)
        * np.abs(projected_upper - projected_lower)
    )

    for start in range(0, USED_SIZE, STRIPE):

        end = min(start + STRIPE, USED_SIZE)

        index_grid = cell_raster[start:end]
        inside = index_grid > 0

        if not np.any(inside):
            continue

        ids = index_grid[inside]

        areas = np.broadcast_to(
            row_areas[start:end, None],
            index_grid.shape
        )[inside]

        h = elevation[start:end][inside]
        s = slope_raw[start:end][inside]
        w = water_hgt[start:end][inside]

        is_land = w == 0
        is_water = w == 255
        classified = is_land | is_water

        valid_elevation = (
            is_land & (h >= -32767)
        )

        valid_slope = (
            is_land & (s <= 9000)
        )

        invalid_slope_samples += int(
            np.count_nonzero(is_land & (s > 9000))
        )

        invalid_water_samples += int(
            np.count_nonzero(~classified)
        )

        def accumulate(target, chosen, values=None):
            if not np.any(chosen):
                return

            selected_ids = ids[chosen]
            selected_areas = areas[chosen]

            if values is not None:
                selected_areas = (
                    selected_areas * values[chosen]
                )

            target[:] += np.bincount(
                selected_ids,
                weights=selected_areas,
                minlength=N + 1
            )

        accumulate(
            covered_area,
            np.ones(len(ids), dtype=bool)
        )

        accumulate(classified_area, classified)
        accumulate(land_area, is_land)
        accumulate(water_area, is_water)

        accumulate(elev_area, valid_elevation)
        accumulate(
            elev_sum,
            valid_elevation,
            h.astype(np.float64)
        )

        accumulate(slope_area, valid_slope)
        accumulate(
            slope_sum,
            valid_slope,
            s.astype(np.float64) / 100.0
        )

        accumulate(
            steep5_area,
            valid_slope & (s >= 500)
        )

        accumulate(
            steep15_area,
            valid_slope & (s >= 1500)
        )

        # Minimum and maximum valid land elevation.

        if np.any(valid_elevation):
            np.minimum.at(
                elev_min,
                ids[valid_elevation],
                h[valid_elevation]
            )

            np.maximum.at(
                elev_max,
                ids[valid_elevation],
                h[valid_elevation]
            )

        if np.any(valid_slope):
            np.maximum.at(
                slope_max,
                ids[valid_slope],
                s[valid_slope] / 100.0
            )

    print(
        f"{tile_number:02d}/39 {tile}: processed",
        flush=True
    )

    del elevation, slope_raw, water_hgt, water_sc, cell_raster


# ==========================================
# BUILD CELL-LEVEL TERRAIN DATA
# ==========================================

print("\n========== CREATING TERRAIN MATRIX ==========")

records = []

for i, cell_id in enumerate(cell_ids, start=1):

    coverage_fraction = (
        covered_area[i] / grid_area[i - 1]
    )

    mean_elev = (
        elev_sum[i] / elev_area[i]
        if elev_area[i] > 0 else np.nan
    )

    mean_slope = (
        slope_sum[i] / slope_area[i]
        if slope_area[i] > 0 else np.nan
    )

    water_pct = (
        100 * water_area[i] / classified_area[i]
        if classified_area[i] > 0 else np.nan
    )

    steep5_pct = (
        100 * steep5_area[i] / slope_area[i]
        if slope_area[i] > 0 else np.nan
    )

    steep15_pct = (
        100 * steep15_area[i] / slope_area[i]
        if slope_area[i] > 0 else np.nan
    )

    record = {
        "cell_id": cell_id,
        "source_coverage_pct": numeric(
            min(coverage_fraction, 1.0) * 100, 2
        ),
        "water_pct": numeric(water_pct, 2),
        "land_pct": numeric(
            100 - water_pct, 2
        ),
        "mean_elevation_m": numeric(mean_elev),
        "min_elevation_m": numeric(elev_min[i]),
        "max_elevation_m": numeric(elev_max[i]),
        "mean_slope_deg": numeric(mean_slope),
        "max_slope_deg": numeric(slope_max[i]),
        "slope_ge_5_pct": numeric(steep5_pct, 2),
        "slope_ge_15_pct": numeric(steep15_pct, 2),
        "elevation_valid_land_pct": numeric(
            100 * elev_area[i] / land_area[i]
            if land_area[i] > 0 else np.nan, 2
        ),
        "slope_valid_land_pct": numeric(
            100 * slope_area[i] / land_area[i]
            if land_area[i] > 0 else np.nan, 2
        )
    }

    records.append(record)


# ==========================================
# QUALITY CONTROL
# ==========================================

land_cells = sum(
    r["mean_elevation_m"] is not None
    for r in records
)

slope_cells = sum(
    r["mean_slope_deg"] is not None
    for r in records
)

missing_coverage = sum(
    r["source_coverage_pct"] < 95
    for r in records
)

raw_coverage_ratios = (
    covered_area[1:] / grid_area
)

report = {
    "status": "complete_with_coverage_review"
        if missing_coverage else "complete",
    "source": ["NASADEM_HGT V001", "NASADEM_SC V001"],
    "tile_pairs": len(tiles),
    "grid_cells": N,
    "cells_with_elevation": land_cells,
    "cells_with_slope": slope_cells,
    "cells_below_95_percent_coverage": missing_coverage,
    "min_raw_coverage_fraction": float(
        raw_coverage_ratios.min()
    ),
    "max_raw_coverage_fraction": float(
        raw_coverage_ratios.max()
    ),
    "water_mask_mismatches": mask_mismatches,
    "invalid_slope_samples": invalid_slope_samples,
    "invalid_water_mask_samples": invalid_water_samples,
    "method": (
        "Area-weighted raster-center assignment, "
        "using sample areas in EPSG:6933. "
        "Not exact pixel-polygon intersection."
    ),
    "shared_tile_edges": (
        "Southern and eastern raster posts excluded "
        "to avoid duplicate boundary samples."
    ),
    "study_window_bbox": [66.0, 23.5, 71.5, 28.5],
    "notes": [
        "Elevations are land-only, in meters relative to EGM96.",
        "Slope statistics are land-only and measured in degrees.",
        "Water fraction uses classified NASADEM sample coverage.",
        "Null values indicate unavailable measurements.",
        "Missing tiles or water-only locations are not zero elevation.",
        "5 km is the analysis grid, not the source DEM resolution."
    ]
}

payload = {
    "project": "Earth Detective",
    "dataset": "NASADEM V001",
    "cell_count": N,
    "cells": records
}

manifest = {
    "dataset": "NASADEM V001",
    "region": "Sindh study window, Pakistan",
    "grid_cell_count": N,
    "source_spacing": "1 arc-second",
    "analysis_grid": "5 km EPSG:6933",
    "terrain_data_url": "/data/terrain/terrain_by_cell.json",
    "grid_geojson_url":
        "/data/grids/sindh_study_window_grid_5km.geojson",
    "join_key": "cell_id",
    "elevation_units": "m above EGM96",
    "slope_units": "degrees",
    "coverage_status": report["status"],
    "limitations": [
        "Raster-center area approximation for grid aggregation.",
        "Terrain is static, not an August 2022 measurement.",
        "Missing values and partial coverage must be displayed.",
        "Elevation and slope alone do not predict flooding."
    ]
}

save_json(
    PUBLIC / "terrain_by_cell.json",
    payload
)

save_json(
    PROCESSED / "terrain_by_cell.json",
    payload
)

save_json(
    PUBLIC / "manifest.json",
    manifest
)

save_json(REPORT, report)


print("\n========== TERRAIN INTEGRATION SUMMARY ==========")
print("Tiles processed:", len(tiles))
print("Grid cells:", N)
print("Cells with elevation:", land_cells)
print("Cells with slope:", slope_cells)
print("Cells below 95% coverage:", missing_coverage)
print("Water-mask differences:", mask_mismatches)
print("Invalid slope samples:", invalid_slope_samples)
print("Invalid water codes:", invalid_water_samples)
print("Minimum raw coverage:", report["min_raw_coverage_fraction"])
print("Maximum raw coverage:", report["max_raw_coverage_fraction"])
print("Status:", report["status"])
print("Output:", PUBLIC / "terrain_by_cell.json")
print("Report:", REPORT)