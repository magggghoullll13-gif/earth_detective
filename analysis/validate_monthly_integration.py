import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import geopandas as gpd
from shapely.geometry import box
from netCDF4 import Dataset, num2date

ROOT = Path(".")
FRAME_DIR = ROOT / "data/processed/rainfall_frames"
GRID_FILE = ROOT / "web/public/data/grids/sindh_study_window_grid_5km.geojson"
MANIFEST = ROOT / "data/processed/metadata/imerg_august_2022_manifest.json"
REPORT = ROOT / "data/processed/metadata/imerg_grid_preflight_report.json"

BASE = datetime(2022, 8, 1, tzinfo=timezone.utc)
EXPECTED_FRAMES = 62


def to_utc(value):
    return datetime(
        value.year, value.month, value.day,
        value.hour, value.minute, value.second,
        value.microsecond, tzinfo=timezone.utc
    )


def expected_filename(start):
    return (
        f"imerg_{start:%Y-%m-%d}_"
        f"{start.hour:02d}-{start.hour + 12:02d}_utc.nc"
    )


print("\n========== EARTH DETECTIVE PREFLIGHT ==========")

# -------------------------------------------------
# 1. VERIFY ALL 62 FRAMES
# -------------------------------------------------

print("\n[1] Checking rainfall frames...")

reference_lat = None
reference_lon = None
reference_lat_bounds = None
reference_lon_bounds = None

frame_records = []
total_complete_pixels = 0
total_incomplete_pixels = 0

for i in range(EXPECTED_FRAMES):

    start = BASE + timedelta(hours=12 * i)
    end = start + timedelta(hours=12)

    path = FRAME_DIR / expected_filename(start)

    if not path.exists():
        raise FileNotFoundError(f"Missing frame: {path}")

    with Dataset(path, "r") as ds:

        lat = np.asarray(ds.variables["lat"][:])
        lon = np.asarray(ds.variables["lon"][:])

        lat_bounds = np.asarray(ds.variables["lat_bounds"][:]) if "lat_bounds" in ds.variables else np.column_stack((lat - np.median(np.diff(lat))/2, lat + np.median(np.diff(lat))/2))
        lon_bounds = np.asarray(ds.variables["lon_bounds"][:]) if "lon_bounds" in ds.variables else np.column_stack((lon - np.median(np.diff(lon))/2, lon + np.median(np.diff(lon))/2))

        if reference_lat is None:
            reference_lat = lat.copy()
            reference_lon = lon.copy()
            reference_lat_bounds = lat_bounds.copy()
            reference_lon_bounds = lon_bounds.copy()
        else:
            assert np.allclose(lat, reference_lat, atol=1e-5)
            assert np.allclose(lon, reference_lon, atol=1e-5)
            assert np.allclose(lat_bounds, reference_lat_bounds)
            assert np.allclose(lon_bounds, reference_lon_bounds)

        assert np.all(np.diff(lat) > 0)
        assert np.all(np.diff(lon) > 0)

        rain_var = ds.variables["precipitation_12h"]

        assert rain_var.units == "mm"
        assert rain_var.dimensions == ("time", "lat", "lon")
        assert rain_var.shape == (1, len(lat), len(lon))

        time_var = ds.variables["time"]

        bounds = num2date(
            ds.variables["time_bounds"][:],
            units=time_var.units,
            calendar=getattr(time_var, "calendar", "standard")
        )

        actual_start = to_utc(bounds[0, 0])
        actual_end = to_utc(bounds[0, 1])

        assert actual_start == start, (path, actual_start, start)
        assert actual_end == end, (path, actual_end, end)

        rain = np.ma.asarray(rain_var[0, :, :])
        counts = np.asarray(
            ds.variables["valid_interval_count"][:]
        )

        assert counts.shape == rain.shape
        assert np.all((counts >= 0) & (counts <= 24))

        valid_mask = (
            ~np.ma.getmaskarray(rain)
            & np.isfinite(rain.filled(np.nan))
        )

        complete_mask = counts == 24

        assert np.array_equal(valid_mask, complete_mask)

        values = rain.compressed()

        assert np.all(np.isfinite(values))
        assert np.all(values >= 0)

        complete = int(np.count_nonzero(complete_mask))
        incomplete = int(counts.size - complete)

        total_complete_pixels += complete
        total_incomplete_pixels += incomplete

        frame_records.append({
            "frame": i + 1,
            "file": path.name,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "complete_pixels": complete,
            "incomplete_pixels": incomplete,
            "min_mm": float(values.min()) if len(values) else None,
            "max_mm": float(values.max()) if len(values) else None,
            "mean_mm": float(values.mean()) if len(values) else None
        })

    if (i + 1) % 10 == 0:
        print(f"Validated {i + 1}/{EXPECTED_FRAMES} frames")

assert len(frame_records) == EXPECTED_FRAMES

print("All 62 frames validated.")
print("Spatial dimensions:", len(reference_lat), "x", len(reference_lon))
print("Total complete pixel-frame observations:", total_complete_pixels)
print("Total incomplete pixel-frame observations:", total_incomplete_pixels)

# -------------------------------------------------
# 2. VERIFY UNIVERSAL GRID
# -------------------------------------------------

print("\n[2] Checking Universal Grid...")

if not GRID_FILE.exists():
    raise FileNotFoundError(GRID_FILE)

grid = gpd.read_file(GRID_FILE)

assert len(grid) == 12412
assert grid["cell_id"].nunique() == 12412
assert grid.crs is not None
assert grid.crs.to_epsg() == 4326
assert grid.geometry.is_valid.all()
assert not grid.geometry.is_empty.any()

print("Grid cells:", len(grid))
print("Unique IDs:", grid["cell_id"].nunique())
print("CRS:", grid.crs)
print("Invalid geometries:", (~grid.geometry.is_valid).sum())
print("Empty geometries:", grid.geometry.is_empty.sum())

# -------------------------------------------------
# 3. CHECK SPATIAL COVERAGE
# -------------------------------------------------

print("\n[3] Checking IMERG coverage over grid...")

west = float(lon_bounds.min())
east = float(lon_bounds.max())
south = float(lat_bounds.min())
north = float(lat_bounds.max())

pixel_footprint = gpd.GeoSeries(
    [box(west, south, east, north)],
    crs="EPSG:4326"
).to_crs("EPSG:6933").iloc[0]

grid_equal_area = grid.to_crs("EPSG:6933")

coverage = np.array([
    geom.intersection(pixel_footprint).area / geom.area
    for geom in grid_equal_area.geometry
])

coverage = np.clip(coverage, 0, 1)

print("IMERG footprint:")
print("West:", west, "East:", east)
print("South:", south, "North:", north)

print("Minimum cell coverage:", float(coverage.min()))
print("Maximum cell coverage:", float(coverage.max()))
print("Fully covered cells:", int(np.sum(coverage >= 0.9999)))
print("Partially covered cells:", int(np.sum(coverage < 0.9999)))

# -------------------------------------------------
# 4. CHECK MONTHLY MANIFEST
# -------------------------------------------------

print("\n[4] Checking monthly manifest...")

manifest_status = "not_found"

if MANIFEST.exists():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_status = manifest.get("status", "unknown")

    print("Manifest status:", manifest_status)
    print("Manifest frames:", len(manifest.get("frames", [])))

    if manifest_status != "complete":
        print("WARNING: Manifest does not report complete status.")

    if len(manifest.get("frames", [])) != 62:
        print("WARNING: Manifest frame count differs from 62.")
else:
    print("WARNING: Monthly manifest not found.")

# -------------------------------------------------
# 5. SAVE PREFLIGHT REPORT
# -------------------------------------------------

report = {
    "project": "Earth Detective",
    "period": "August 2022",
    "frame_count": EXPECTED_FRAMES,
    "frame_validation": "passed",
    "grid_cell_count": len(grid),
    "grid_validation": "passed",
    "grid_crs": "EPSG:4326",
    "grid_analysis_crs": "EPSG:6933",
    "imerg_resolution": "0.1 degree",
    "imerg_dimensions": [
        len(reference_lat),
        len(reference_lon)
    ],
    "imerg_bounds": {
        "west": west,
        "south": south,
        "east": east,
        "north": north
    },
    "total_complete_pixel_frames": total_complete_pixels,
    "total_incomplete_pixel_frames": total_incomplete_pixels,
    "minimum_grid_coverage": float(coverage.min()),
    "maximum_grid_coverage": float(coverage.max()),
    "fully_covered_cells": int(np.sum(coverage >= 0.9999)),
    "partially_covered_cells": int(np.sum(coverage < 0.9999)),
    "manifest_status": manifest_status,
    "frames": frame_records
}

REPORT.parent.mkdir(parents=True, exist_ok=True)

REPORT.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print("\n========== PREFLIGHT SUCCESS ==========")
print("Frames:", EXPECTED_FRAMES)
print("Grid cells:", len(grid))
print("IMERG resolution: 0.1 degree")
print("Output report:", REPORT)
print("\nReady for area-weighted spatial integration.")
