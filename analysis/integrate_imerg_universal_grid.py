import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import geopandas as gpd
from shapely.geometry import box
from netCDF4 import Dataset, num2date


# ==========================================
# EARTH DETECTIVE
# AREA-WEIGHTED RAINFALL GRID INTEGRATION
# ==========================================

GRID_PATH = Path(
    "web/public/data/grids/sindh_study_window_grid_5km.geojson"
)

FRAME_DIR = Path("data/processed/rainfall_frames")

RAW_FIRST_DIR = Path(
    "data/raw/pakistan/imerg_half_hourly/2022-08-01_00-12"
)

PUBLIC_DIR = Path("web/public/data/rainfall")
FRAMES_PUBLIC = PUBLIC_DIR / "frames"

OVERLAY_DIR = Path("data/processed/overlays")

REPORT_PATH = Path(
    "data/processed/metadata/"
    "rainfall_grid_integration_report.json"
)

START = datetime(2022, 8, 1, tzinfo=timezone.utc)
FRAME_COUNT = 62
MIN_VALID_COVERAGE = 0.999

for directory in [PUBLIC_DIR, FRAMES_PUBLIC, OVERLAY_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, separators=(",", ":"), allow_nan=False),
        encoding="utf-8"
    )
    temp.replace(path)


def frame_filename(start):
    return (
        f"imerg_{start:%Y-%m-%d}_"
        f"{start.hour:02d}-{start.hour + 12:02d}_utc.nc"
    )


def to_utc(value):
    return datetime(
        value.year, value.month, value.day,
        value.hour, value.minute, value.second,
        value.microsecond, tzinfo=timezone.utc
    )


print("\n========== LOADING UNIVERSAL GRID ==========")

grid = gpd.read_file(GRID_PATH)

assert len(grid) == 12412
assert grid["cell_id"].is_unique
assert grid.crs.to_epsg() == 4326
assert grid.geometry.is_valid.all()
assert not grid.geometry.is_empty.any()

cell_ids = grid["cell_id"].astype(str).tolist()

# Equal-area CRS: polygon overlap measured in square meters.
grid_m = grid.to_crs("EPSG:6933")
cell_areas = grid_m.geometry.area.to_numpy()

print("Grid cells:", len(grid))


# ==========================================
# LOAD ORIGINAL NASA PIXEL BOUNDARIES
# ==========================================

print("\n========== LOADING NASA PIXEL BOUNDS ==========")

source_files = sorted(
    RAW_FIRST_DIR.glob("*_Grid_precipitation_subsetted.nc4")
)

if not source_files:
    raise FileNotFoundError(
        "Original NASA first-half-day granules are required."
    )

with Dataset(source_files[0], "r") as ds:
    source = ds.groups["Grid"]

    lat = np.asarray(source.variables["lat"][:], dtype=float)
    lon = np.asarray(source.variables["lon"][:], dtype=float)

    lat_b = np.asarray(
        source.variables["lat_bnds"][:],
        dtype=float
    )

    lon_b = np.asarray(
        source.variables["lon_bnds"][:],
        dtype=float
    )

nlat, nlon = len(lat), len(lon)

assert lat_b.shape == (nlat, 2)
assert lon_b.shape == (nlon, 2)

assert np.isfinite(lat_b).all()
assert np.isfinite(lon_b).all()

assert np.all(
    (lat >= lat_b.min(axis=1) - 0.001)
    & (lat <= lat_b.max(axis=1) + 0.001)
)

assert np.all(
    (lon >= lon_b.min(axis=1) - 0.001)
    & (lon <= lon_b.max(axis=1) + 0.001)
)

print("Original NASA pixel matrix:", nlat, "x", nlon)


# ==========================================
# BUILD SPATIAL PIXEL POLYGONS
# ==========================================

print("\n========== BUILDING AREA WEIGHTS ==========")

pixel_geometries = []

# IMPORTANT:
# Pixel order matches rainfall array flattening:
# first latitude, then longitude.

for i in range(nlat):
    for j in range(nlon):

        west, east = sorted(lon_b[j])
        south, north = sorted(lat_b[i])

        pixel_geometries.append(
            box(west, south, east, north)
        )

pixels = gpd.GeoDataFrame(
    geometry=pixel_geometries,
    crs="EPSG:4326"
).to_crs("EPSG:6933")

pixel_shapes = pixels.geometry
spatial_index = pixels.sindex

cell_indices = []
pixel_indices = []
weight_fractions = []

for cell_idx, cell_geom in enumerate(grid_m.geometry):

    candidates = spatial_index.query(cell_geom)

    for pixel_idx in candidates:

        pixel_idx = int(pixel_idx)

        intersection = cell_geom.intersection(
            pixel_shapes.iloc[pixel_idx]
        )

        overlap_area = intersection.area

        if overlap_area <= 0:
            continue

        cell_indices.append(cell_idx)
        pixel_indices.append(pixel_idx)

        weight_fractions.append(
            overlap_area / cell_areas[cell_idx]
        )

    if (cell_idx + 1) % 2000 == 0:
        print(f"Processed {cell_idx + 1}/{len(grid)} cells")

cell_indices = np.asarray(cell_indices, dtype=np.int32)
pixel_indices = np.asarray(pixel_indices, dtype=np.int32)
weights = np.asarray(weight_fractions, dtype=np.float64)

coverage = np.bincount(
    cell_indices,
    weights=weights,
    minlength=len(grid)
)

print("Spatial intersections:", len(weights))
print("Minimum coverage:", float(coverage.min()))
print("Maximum coverage:", float(coverage.max()))

if coverage.min() < MIN_VALID_COVERAGE:
    raise RuntimeError(
        "Some grid cells have insufficient IMERG coverage."
    )

if coverage.max() > 1.001:
    raise RuntimeError(
        "IMERG pixel overlap weights exceed cell area."
    )

# Save reusable overlay weights.

np.savez_compressed(
    OVERLAY_DIR / "imerg_v07_to_universal_grid_weights.npz",
    cell_indices=cell_indices,
    pixel_indices=pixel_indices,
    weights=weights,
    coverage=coverage,
    cell_ids=np.asarray(cell_ids),
    lat=lat,
    lon=lon,
    lat_bounds=lat_b,
    lon_bounds=lon_b
)

save_json(
    PUBLIC_DIR / "cell_index.json",
    {
        "cellIds": cell_ids,
        "sourceCoverageFraction": [
            round(float(v), 6)
            for v in coverage
        ],
        "gridGeojsonUrl":
            "/data/grids/sindh_study_window_grid_5km.geojson",
        "sourceResolution": "0.1 degree",
        "analysisGridSizeMeters": 5000,
        "spatialMethod": "area-weighted overlap in EPSG:6933",
        "note": (
            "5 km cells are analysis zones, "
            "not independent 5 km NASA observations."
        )
    }
)


# ==========================================
# PROCESS ALL 62 FRAMES
# ==========================================

print("\n========== INTEGRATING 62 FRAMES ==========")

manifest_frames = []
monthly_total = np.zeros(len(grid), dtype=np.float64)
monthly_valid = np.ones(len(grid), dtype=bool)

for frame_idx in range(FRAME_COUNT):

    start = START + timedelta(hours=12 * frame_idx)
    end = start + timedelta(hours=12)

    file_path = FRAME_DIR / frame_filename(start)

    if not file_path.exists():
        raise FileNotFoundError(file_path)

    with Dataset(file_path, "r") as ds:

        np.testing.assert_allclose(
            ds.variables["lat"][:],
            lat,
            atol=1e-5
        )

        np.testing.assert_allclose(
            ds.variables["lon"][:],
            lon,
            atol=1e-5
        )

        if "lat_bounds" in ds.variables:
            np.testing.assert_allclose(
                ds.variables["lat_bounds"][:],
                lat_b,
                atol=1e-5
            )

        if "lon_bounds" in ds.variables:
            np.testing.assert_allclose(
                ds.variables["lon_bounds"][:],
                lon_b,
                atol=1e-5
            )

        time_var = ds.variables["time"]

        time_bounds = num2date(
            ds.variables["time_bounds"][:],
            units=time_var.units,
            calendar=getattr(
                time_var, "calendar", "standard"
            )
        )

        assert to_utc(time_bounds[0, 0]) == start
        assert to_utc(time_bounds[0, 1]) == end

        rain_var = ds.variables["precipitation_12h"]

        assert rain_var.units == "mm"
        assert rain_var.dimensions == ("time", "lat", "lon")

        rainfall = np.ma.asarray(
            rain_var[0, :, :],
            dtype=np.float64
        ).filled(np.nan)

        counts = np.asarray(
            ds.variables["valid_interval_count"][:]
        )

    assert rainfall.shape == (nlat, nlon)
    assert counts.shape == rainfall.shape

    values = rainfall.ravel()

    # A source pixel is valid only when all 24
    # half-hourly observations were available.

    valid = (
        (counts.ravel() == 24)
        & np.isfinite(values)
        & (values >= 0)
    )

    clean_values = np.where(valid, values, 0.0)

    # Area-weighted rainfall numerator.

    numerator = np.bincount(
        cell_indices,
        weights=(
            weights * clean_values[pixel_indices]
        ),
        minlength=len(grid)
    )

    # Fraction of each target cell covered by
    # valid NASA observations.

    valid_coverage = np.bincount(
        cell_indices,
        weights=(
            weights * valid[pixel_indices].astype(float)
        ),
        minlength=len(grid)
    )

    complete = valid_coverage >= MIN_VALID_COVERAGE

    cell_rain = np.full(
        len(grid),
        np.nan,
        dtype=np.float64
    )

    # Normalize by valid covered area.
    cell_rain[complete] = (
        numerator[complete] / valid_coverage[complete]
    )

    if np.any(cell_rain[complete] < -1e-8):
        raise ValueError("Negative cell rainfall value.")

    # A weighted average should never exceed
    # the range of the valid source pixels.

    source_valid_values = values[valid]

    if source_valid_values.size == 0:
        raise RuntimeError("Frame has no valid source pixels.")

    if np.any(complete):
        assert cell_rain[complete].min() >= (
            source_valid_values.min() - 1e-5
        )
        assert cell_rain[complete].max() <= (
            source_valid_values.max() + 1e-5
        )

    monthly_total += np.where(
        complete,
        cell_rain,
        0.0
    )

    monthly_valid &= complete

    output_name = (
        f"rainfall_{start:%Y-%m-%d}_"
        f"{start.hour:02d}-{start.hour + 12:02d}_utc.json"
    )

    # Array indices correspond to cell_index.json.
    # Null means insufficient valid spatial coverage.

    output_values = [
        round(float(v), 4) if np.isfinite(v) else None
        for v in cell_rain
    ]

    save_json(
        FRAMES_PUBLIC / output_name,
        {
            "frame": frame_idx + 1,
            "startUtc": iso(start),
            "endUtc": iso(end),
            "variable": "precipitation_12h",
            "units": "mm",
            "valuesMm": output_values
        }
    )

    valid_values = cell_rain[complete]

    frame_summary = {
        "frame": frame_idx + 1,
        "startUtc": iso(start),
        "endUtc": iso(end),
        "url": "/data/rainfall/frames/" + output_name,
        "validCells": int(complete.sum()),
        "missingCells": int((~complete).sum()),
        "minimumMm": (
            float(valid_values.min())
            if valid_values.size else None
        ),
        "maximumMm": (
            float(valid_values.max())
            if valid_values.size else None
        ),
        "meanMm": (
            float(valid_values.mean())
            if valid_values.size else None
        )
    }

    manifest_frames.append(frame_summary)

    print(
        f"Frame {frame_idx + 1:02d}/62: "
        f"valid={complete.sum()}, "
        f"missing={(~complete).sum()}"
    )


# ==========================================
# MONTHLY TOTAL PER CELL
# ==========================================

monthly_total[~monthly_valid] = np.nan

save_json(
    PUBLIC_DIR / "monthly_total_mm.json",
    {
        "period": "August 2022",
        "variable": "monthly_precipitation",
        "units": "mm",
        "valuesMm": [
            round(float(v), 4) if np.isfinite(v) else None
            for v in monthly_total
        ],
        "completeFrameCountRequired": 62
    }
)

valid_monthly = monthly_valid & np.isfinite(monthly_total)

monthly_mean = None

if np.any(valid_monthly):
    monthly_mean = float(
        np.average(
            monthly_total[valid_monthly],
            weights=cell_areas[valid_monthly]
        )
    )


# ==========================================
# EXPORT FRONTEND MANIFEST
# ==========================================

manifest = {
    "project": "Earth Detective",
    "dataset": "NASA GPM IMERG Final Run V07",
    "region": "Sindh study window, Pakistan",
    "periodStartUtc": iso(START),
    "periodEndUtc": iso(
        START + timedelta(days=31)
    ),
    "frameDurationHours": 12,
    "frameCount": 62,
    "cellCount": len(grid),
    "units": "mm",
    "cellIndexUrl": "/data/rainfall/cell_index.json",
    "monthlyTotalUrl": "/data/rainfall/monthly_total_mm.json",
    "frames": manifest_frames,
    "scientificLimitations": [
        "Native IMERG resolution is 0.1 degree.",
        "The Universal Grid is a 5 km analysis framework.",
        "Area weighting does not improve satellite resolution.",
        "Rainfall alone does not establish flooding.",
        "This is the rectangular Sindh study window."
    ]
}

save_json(
    PUBLIC_DIR / "manifest.json",
    manifest
)

save_json(
    REPORT_PATH,
    {
        "status": "complete",
        "frames": 62,
        "cells": len(grid),
        "cellFrameValues": len(grid) * 62,
        "spatialIntersections": len(weights),
        "minimumSourceCoverage": float(coverage.min()),
        "maximumSourceCoverage": float(coverage.max()),
        "monthlyAreaWeightedMeanMm": monthly_mean,
        "monthlyFullyValidCells": int(monthly_valid.sum()),
        "method": "EPSG:6933 pixel-cell area weighting",
        "referenceGrid": str(GRID_PATH),
        "sourcePixelBounds": str(source_files[0]),
        "monthlyGiovanniComparison": (
            "Not performed: source raster grid alignment "
            "must be reconciled first."
        )
    }
)

print("\n========== INTEGRATION COMPLETED ==========")
print("Frames:", FRAME_COUNT)
print("Cells:", len(grid))
print("Cell-frame values:", len(grid) * FRAME_COUNT)
print("Spatial intersections:", len(weights))
print("Monthly area-weighted mean:", monthly_mean)
print("Manifest:", PUBLIC_DIR / "manifest.json")
print("Report:", REPORT_PATH)