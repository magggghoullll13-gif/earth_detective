import json
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import earthaccess

from netCDF4 import Dataset, num2date
from harmony import BBox, Client, Collection, Request


# =====================================================
# EARTH DETECTIVE - FULL AUGUST 2022 PIPELINE
# =====================================================

COLLECTION_ID = "C2723754847-GES_DISC"
BBOX = (66.0, 23.5, 71.5, 28.5)

BASE = datetime(2022, 8, 1, tzinfo=timezone.utc)

TOTAL_GRANULES = 1488
GRANULES_PER_FRAME = 24
TOTAL_FRAMES = 62

RAW_ROOT = Path("data/raw/pakistan/imerg_half_hourly")
OUTPUT_ROOT = Path("data/processed/rainfall_frames")
META_ROOT = Path("data/processed/metadata")

FIRST_FRAME = OUTPUT_ROOT / "imerg_2022-08-01_00-12_utc.nc"

MANIFEST = META_ROOT / "imerg_august_2022_manifest.json"

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
META_ROOT.mkdir(parents=True, exist_ok=True)
RAW_ROOT.mkdir(parents=True, exist_ok=True)


# =====================================================
# UTILITIES
# =====================================================

def parse_utc(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def cftime_to_utc(value):
    return datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
        tzinfo=timezone.utc
    )


def frame_name(start):
    return (
        f"imerg_{start:%Y-%m-%d}_"
        f"{start.hour:02d}-{start.hour + 12:02d}_utc.nc"
    )


def frame_raw_dir(start):
    name = (
        f"{start:%Y-%m-%d}_"
        f"{start.hour:02d}-{start.hour + 12:02d}"
    )
    return RAW_ROOT / name


def save_manifest(manifest):
    temp = MANIFEST.with_suffix(".tmp")

    temp.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8"
    )

    temp.replace(MANIFEST)


# =====================================================
# VALIDATE EXISTING OUTPUT FRAME
# =====================================================

def inspect_output(path, expected_start, ref_lat=None, ref_lon=None):

    with Dataset(path, "r") as ds:

        lat = np.asarray(ds.variables["lat"][:], dtype=np.float64)
        lon = np.asarray(ds.variables["lon"][:], dtype=np.float64)

        if ref_lat is not None:
            if not np.allclose(lat, ref_lat, atol=1e-5):
                raise ValueError("Output latitude grid mismatch.")

            if not np.allclose(lon, ref_lon, atol=1e-5):
                raise ValueError("Output longitude grid mismatch.")

        rain_var = ds.variables["precipitation_12h"]

        if rain_var.units != "mm":
            raise ValueError("Output rainfall units are not mm.")

        rain = np.ma.asarray(rain_var[:])

        if rain.shape != (1, len(lat), len(lon)):
            raise ValueError("Unexpected output dimensions.")

        time_var = ds.variables["time"]

        bounds = num2date(
            ds.variables["time_bounds"][:],
            units=time_var.units,
            calendar=getattr(time_var, "calendar", "standard")
        )

        actual_start = cftime_to_utc(bounds[0, 0])
        actual_end = cftime_to_utc(bounds[0, 1])

        expected_end = expected_start + timedelta(hours=12)

        if actual_start != expected_start or actual_end != expected_end:
            raise ValueError("Output temporal coverage mismatch.")

        counts = np.asarray(
            ds.variables["valid_interval_count"][:]
        )

        if counts.shape != (len(lat), len(lon)):
            raise ValueError("Invalid interval-count dimensions.")

        if np.any(counts > 24):
            raise ValueError("Invalid interval counts.")

        values = rain.compressed()

        complete_pixels = int(np.count_nonzero(counts == 24))
        incomplete_pixels = int(counts.size - complete_pixels)

        if len(values) != complete_pixels:
            raise ValueError("Rainfall masks and interval counts disagree.")

        if len(values) == 0:
            raise ValueError("Frame has no complete pixels.")

        return {
            "shape": list(rain.shape),
            "complete_pixels": complete_pixels,
            "incomplete_pixels": incomplete_pixels,
            "minimum_mm": float(values.min()),
            "maximum_mm": float(values.max()),
            "mean_mm": float(values.mean()),
            "latitude_count": len(lat),
            "longitude_count": len(lon)
        }, lat, lon


# =====================================================
# PROCESS ONE 12-HOUR FRAME
# =====================================================

def aggregate_frame(files, expected_times, start, output, ref_lat, ref_lon, granule_names):

    records = []

    reference_lat_bounds = None
    reference_lon_bounds = None

    for file_path in files:

        with Dataset(file_path, "r") as ds:

            grid = ds.groups["Grid"]

            lat = np.asarray(
                grid.variables["lat"][:],
                dtype=np.float64
            )

            lon = np.asarray(
                grid.variables["lon"][:],
                dtype=np.float64
            )

            if not np.allclose(lat, ref_lat, atol=1e-5):
                raise ValueError("Input latitude grid mismatch.")

            if not np.allclose(lon, ref_lon, atol=1e-5):
                raise ValueError("Input longitude grid mismatch.")

            lat_bounds = np.asarray(grid.variables["lat_bnds"][:])
            lon_bounds = np.asarray(grid.variables["lon_bnds"][:])

            if reference_lat_bounds is None:
                reference_lat_bounds = lat_bounds.copy()
                reference_lon_bounds = lon_bounds.copy()
            else:
                if not np.allclose(lat_bounds, reference_lat_bounds):
                    raise ValueError("Latitude pixel bounds changed.")

                if not np.allclose(lon_bounds, reference_lon_bounds):
                    raise ValueError("Longitude pixel bounds changed.")

            time_var = grid.variables["time"]

            decoded = num2date(
                grid.variables["time_bnds"][:],
                units=time_var.units,
                calendar=getattr(time_var, "calendar", "standard")
            )

            interval_start = cftime_to_utc(decoded[0, 0])
            interval_end = cftime_to_utc(decoded[0, 1])

            if interval_end - interval_start != timedelta(minutes=30):
                raise ValueError("Unexpected source interval duration.")

            variable = grid.variables["precipitation"]

            if variable.units != "mm/hr":
                raise ValueError("Unexpected source precipitation units.")

            if variable.dimensions != ("time", "lon", "lat"):
                raise ValueError("Unexpected source array ordering.")

            raw = np.ma.asarray(
                variable[0, :, :],
                dtype=np.float64
            )

            # Source order: longitude, latitude.
            # Output processing order: latitude, longitude.

            rainfall = raw.T

            data = np.asarray(
                rainfall.filled(np.nan),
                dtype=np.float64
            )

            valid = (
                ~np.ma.getmaskarray(rainfall)
                & np.isfinite(data)
            )

            fill = getattr(variable, "_FillValue", None)

            if fill is not None:
                valid &= data != fill

            missing_code = getattr(variable, "CodeMissingValue", None)

            if missing_code is not None:
                valid &= data != missing_code

            if np.any(data[valid] < 0):
                raise ValueError("Negative valid precipitation value.")

            records.append({
                "start": interval_start,
                "end": interval_end,
                "data": data,
                "valid": valid
            })

    records.sort(key=lambda r: r["start"])

    actual_times = [r["start"] for r in records]

    if actual_times != expected_times:
        raise ValueError("Missing, duplicate or incorrectly ordered observations.")

    if len(records) != 24:
        raise ValueError("Expected exactly 24 source observations.")

    # Accumulation.

    shape = records[0]["data"].shape

    rainfall_sum = np.zeros(shape, dtype=np.float64)
    valid_count = np.zeros(shape, dtype=np.uint8)

    for record in records:

        rainfall_sum += np.where(
            record["valid"],
            record["data"] * 0.5,
            0.0
        )

        valid_count += record["valid"].astype(np.uint8)

    complete = valid_count == 24

    rainfall_12h = np.where(
        complete,
        rainfall_sum,
        np.nan
    )

    if not np.any(complete):
        raise ValueError("No complete spatial pixels.")

    end = start + timedelta(hours=12)

    # Write NetCDF.

    with Dataset(output, "w", format="NETCDF4") as out:

        out.createDimension("time", 1)
        out.createDimension("lat", len(ref_lat))
        out.createDimension("lon", len(ref_lon))
        out.createDimension("nv", 2)

        lat_var = out.createVariable("lat", "f4", ("lat",))
        lon_var = out.createVariable("lon", "f4", ("lon",))

        lat_var.units = "degrees_north"
        lon_var.units = "degrees_east"

        lat_var[:] = ref_lat
        lon_var[:] = ref_lon

        lat_bnds = out.createVariable(
            "lat_bounds", "f4", ("lat", "nv")
        )

        lon_bnds = out.createVariable(
            "lon_bounds", "f4", ("lon", "nv")
        )

        lat_bnds[:] = reference_lat_bounds
        lon_bnds[:] = reference_lon_bounds

        time_var = out.createVariable("time", "f8", ("time",))

        time_var.units = "seconds since 1970-01-01 00:00:00 UTC"
        time_var.calendar = "standard"
        time_var.bounds = "time_bounds"

        time_var[0] = start.timestamp()

        time_bounds = out.createVariable(
            "time_bounds", "f8", ("time", "nv")
        )

        time_bounds.units = time_var.units
        time_bounds.calendar = "standard"

        time_bounds[0, :] = [
            start.timestamp(),
            end.timestamp()
        ]

        precipitation = out.createVariable(
            "precipitation_12h",
            "f4",
            ("time", "lat", "lon"),
            zlib=True,
            complevel=4,
            fill_value=np.float32(-9999.9)
        )

        precipitation.units = "mm"
        precipitation.long_name = "Accumulated precipitation over 12 hours"
        precipitation.coordinates = "time lat lon"
        precipitation[0, :, :] = np.ma.masked_invalid(rainfall_12h)

        count_var = out.createVariable(
            "valid_interval_count",
            "u1",
            ("lat", "lon")
        )

        count_var.units = "intervals"
        count_var.long_name = "Number of valid half-hourly observations"
        count_var[:, :] = valid_count

        fraction_var = out.createVariable(
            "valid_interval_fraction",
            "f4",
            ("lat", "lon")
        )

        fraction_var.units = "1"
        fraction_var[:, :] = valid_count.astype(np.float32) / 24.0

        out.title = "Earth Detective - IMERG 12-hour rainfall frame"
        out.source_product = "GPM_3IMERGHH"
        out.source_version = "V07"
        out.source_variable = "Grid/precipitation"
        out.source_units = "mm/hr"
        out.temporal_aggregation = "sum(rate * 0.5 hours)"
        out.source_granule_count = 24
        out.source_granules_json = json.dumps(granule_names)
        out.native_spatial_resolution = "0.1 degree"
        out.source_array_order = "time,longitude,latitude"
        out.output_array_order = "time,latitude,longitude"
        out.missing_data_policy = "Incomplete pixels are masked, never filled with zero."
        out.time_coverage_start = start.isoformat()
        out.time_coverage_end = end.isoformat()
        out.bounding_box_west_south_east_north = json.dumps(BBOX)
        out.monthly_reference_note = (
            "No pixelwise comparison performed: Giovanni reference grid "
            "has a different longitude dimension."
        )

    print("Created:", output)


# =====================================================
# MAIN PIPELINE
# =====================================================

print("\n==============================================")
print("EARTH DETECTIVE - AUGUST 2022 IMERG PIPELINE")
print("==============================================")

print("\nAuthenticating with NASA Earthdata...")

earthaccess.login(
    strategy="interactive",
    persist=True
)

# Search metadata for all granules.

print("\nSearching NASA catalogue...")

granules = earthaccess.search_data(
    short_name="GPM_3IMERGHH",
    version="07",
    daac="GES_DISC",
    cloud_hosted=True,
    temporal=(
        "2022-08-01T00:00:00",
        "2022-08-31T23:59:59"
    ),
    bounding_box=BBOX,
    count=-1
)

print("Granules found:", len(granules))

if len(granules) != TOTAL_GRANULES:
    raise RuntimeError("Expected exactly 1,488 granules.")

granule_map = {}

for granule in granules:

    temporal = granule["umm"]["TemporalExtent"]["RangeDateTime"]

    start = parse_utc(temporal["BeginningDateTime"])

    if start in granule_map:
        raise RuntimeError(f"Duplicate granule timestamp: {start}")

    granule_map[start] = granule

expected_all = [
    BASE + timedelta(minutes=30 * i)
    for i in range(TOTAL_GRANULES)
]

if set(granule_map) != set(expected_all):
    missing = set(expected_all) - set(granule_map)

    raise RuntimeError(
        f"Catalogue timestamps incomplete. Missing: {len(missing)}"
    )

print("Temporal validation: 1,488/1,488 passed.")

# Require the previously validated first frame.
# Never redownload it.

if not FIRST_FRAME.exists():
    raise RuntimeError(
        "Validated first frame is missing. "
        "Restore it before continuing."
    )

first_summary, reference_lat, reference_lon = inspect_output(
    FIRST_FRAME,
    BASE
)

print("\nFirst validated frame preserved.")
print("Reference spatial grid:", first_summary["shape"])

# Prepare manifest.

manifest = {
    "project": "Earth Detective",
    "product": "GPM_3IMERGHH",
    "version": "V07",
    "run": "Final",
    "region": "Sindh, Pakistan",
    "bounding_box": BBOX,
    "period": "August 2022",
    "source_resolution": "0.1 degree",
    "source_temporal_resolution": "30 minutes",
    "target_temporal_resolution": "12 hours",
    "expected_frames": TOTAL_FRAMES,
    "expected_source_granules": TOTAL_GRANULES,
    "aggregation": "sum(precipitation_rate_mm_per_hour * 0.5)",
    "frames": []
}

# Process all 62 frames.
# Existing valid output frames are skipped.

for frame_index in range(TOTAL_FRAMES):

    start = BASE + timedelta(hours=12 * frame_index)
    end = start + timedelta(hours=12)

    output = OUTPUT_ROOT / frame_name(start)
    raw_dir = frame_raw_dir(start)

    expected_times = [
        start + timedelta(minutes=30 * i)
        for i in range(24)
    ]

    selected_granules = [
        granule_map[t]
        for t in expected_times
    ]

    granule_names = [
        g["umm"]["GranuleUR"]
        for g in selected_granules
    ]

    print("\n")
    print("=" * 60)
    print(f"FRAME {frame_index + 1}/{TOTAL_FRAMES}")
    print("Start:", start)
    print("End:", end)
    print("=" * 60)

    # Skip existing valid frame.

    if output.exists():

        print("Existing output found. Validating and reusing...")

        summary, _, _ = inspect_output(
            output,
            start,
            reference_lat,
            reference_lon
        )

        status = "reused_existing"

    else:

        raw_dir.mkdir(parents=True, exist_ok=True)

        raw_files = list(
            raw_dir.glob("*_Grid_precipitation_subsetted.nc4")
        )

        # Download only if this frame does not already
        # have all 24 spatial subsets.

        if len(raw_files) != 24:

            print("Spatial subsets incomplete.")
            print("Preparing NASA Harmony request...")

            last_error = None

            for attempt in range(1, 4):

                print(f"\nHarmony attempt {attempt}/3")

                # Remove only incomplete files in this
                # frame's dedicated folder.

                for partial in raw_dir.glob(
                    "*_Grid_precipitation_subsetted.nc4"
                ):
                    partial.unlink()

                try:

                    request = Request(
                        collection=Collection(id=COLLECTION_ID),
                        granule_name=granule_names,
                        spatial=BBox(*BBOX),
                        variables=["Grid/precipitation"],
                        format="application/netcdf",
                        max_results=24
                    )

                    if not request.is_valid():
                        raise RuntimeError(
                            str(request.error_messages())
                        )

                    client = Client()

                    job_id = client.submit(request)

                    print("Harmony job:", job_id)

                    client.wait_for_processing(
                        job_id,
                        show_progress=True
                    )

                    futures = client.download_all(
                        job_id,
                        directory=str(raw_dir),
                        overwrite=False
                    )

                    for future in futures:
                        future.result()

                    raw_files = list(
                        raw_dir.glob(
                            "*_Grid_precipitation_subsetted.nc4"
                        )
                    )

                    if len(raw_files) != 24:
                        raise RuntimeError(
                            f"Expected 24 outputs, got {len(raw_files)}"
                        )

                    print("24 spatial granules downloaded.")

                    break

                except Exception as error:

                    last_error = error

                    print("Attempt failed:", error)

                    for partial in raw_dir.glob(
                        "*_Grid_precipitation_subsetted.nc4"
                    ):
                        partial.unlink()

                    if attempt < 3:
                        delay = 15 * attempt

                        print(f"Retrying in {delay} seconds...")
                        time.sleep(delay)

            else:
                raise RuntimeError(
                    f"Failed to download frame {start}: {last_error}"
                )

        else:
            print("Reusing existing 24 raw spatial granules.")

        # Aggregate and validate.

        raw_files = list(
            raw_dir.glob("*_Grid_precipitation_subsetted.nc4")
        )

        aggregate_frame(
            raw_files,
            expected_times,
            start,
            output,
            reference_lat,
            reference_lon,
            granule_names
        )

        summary, _, _ = inspect_output(
            output,
            start,
            reference_lat,
            reference_lon
        )

        status = "created"

        # Be gentle with Harmony between jobs.

        time.sleep(5)

    frame_record = {
        "frame_number": frame_index + 1,
        "status": status,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "file": output.as_posix(),
        "source_granule_count": 24,
        "source_granules": granule_names,
        **summary
    }

    manifest["frames"].append(frame_record)

    # Save progress after every completed frame.

    manifest["completed_frames"] = len(manifest["frames"])
    manifest["status"] = "in_progress"

    save_manifest(manifest)

    print("\nFRAME VALIDATED")
    print("Complete pixels:", summary["complete_pixels"])
    print("Incomplete pixels:", summary["incomplete_pixels"])
    print("Minimum:", summary["minimum_mm"], "mm")
    print("Maximum:", summary["maximum_mm"], "mm")
    print("Mean:", summary["mean_mm"], "mm")


# =====================================================
# FINAL MONTHLY VALIDATION
# =====================================================

print("\n==============================================")
print("FINAL AUGUST VALIDATION")
print("==============================================")

if len(manifest["frames"]) != TOTAL_FRAMES:
    raise RuntimeError("Not all 62 frames were completed.")

if len({
    f["start_utc"]
    for f in manifest["frames"]
}) != TOTAL_FRAMES:
    raise RuntimeError("Duplicate output frame timestamps.")

if sum(
    f["source_granule_count"]
    for f in manifest["frames"]
) != TOTAL_GRANULES:
    raise RuntimeError("Source granule accounting failed.")

manifest["status"] = "complete"
manifest["completed_frames"] = TOTAL_FRAMES

save_manifest(manifest)

print("\nSUCCESS!")
print("Total frames:", TOTAL_FRAMES)
print("Total source granules:", TOTAL_GRANULES)
print("First frame:", manifest["frames"][0]["file"])
print("Last frame:", manifest["frames"][-1]["file"])
print("Manifest:", MANIFEST)
print("\nEarth Detective August rainfall pipeline completed.")