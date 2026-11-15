
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
from netCDF4 import Dataset, num2date


# ==========================================
# EARTH DETECTIVE
# FIRST 12-HOUR RAINFALL AGGREGATION
# ==========================================

INPUT_DIR = Path(
    "data/raw/pakistan/imerg_half_hourly/"
    "2022-08-01_00-12"
)

OUTPUT_FILE = Path(
    "data/processed/rainfall_frames/"
    "imerg_2022-08-01_00-12_utc.nc"
)

EXPECTED_INTERVALS = 24
INTERVAL_HOURS = 0.5

EXPECTED_START = datetime(
    2022, 8, 1, 0, 0,
    tzinfo=timezone.utc
)

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


def to_utc_datetime(value):
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


# ==========================================
# 1. FIND INPUT FILES
# ==========================================

files = list(
    INPUT_DIR.glob(
        "*_Grid_precipitation_subsetted.nc4"
    )
)

print("========== INPUT VALIDATION ==========")
print("Files found:", len(files))

if len(files) != EXPECTED_INTERVALS:
    raise RuntimeError(
        f"Expected 24 files, found {len(files)}"
    )


# ==========================================
# 2. READ AND VALIDATE EVERY GRANULE
# ==========================================

records = []

reference_lat = None
reference_lon = None

for index, file_path in enumerate(files, start=1):

    print(
        f"Reading {index}/{EXPECTED_INTERVALS}: "
        f"{file_path.name}"
    )

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

        # Check coordinate consistency.

        if reference_lat is None:

            reference_lat = lat.copy()
            reference_lon = lon.copy()

        else:

            if not np.allclose(
                lat,
                reference_lat,
                atol=1e-5
            ):
                raise ValueError(
                    "Latitude coordinates differ."
                )

            if not np.allclose(
                lon,
                reference_lon,
                atol=1e-5
            ):
                raise ValueError(
                    "Longitude coordinates differ."
                )

        # Read temporal bounds.

        time_var = grid.variables["time"]
        bounds_var = grid.variables["time_bnds"]

        calendar = getattr(
            time_var,
            "calendar",
            "standard"
        )

        decoded = num2date(
            bounds_var[:],
            units=time_var.units,
            calendar=calendar,
            only_use_cftime_datetimes=True
        )

        start = to_utc_datetime(decoded[0, 0])
        end = to_utc_datetime(decoded[0, 1])

        if end - start != timedelta(minutes=30):
            raise ValueError(
                f"Unexpected time interval: {file_path.name}"
            )

        # Read precipitation.

        precipitation_var = grid.variables[
            "precipitation"
        ]

        if precipitation_var.units != "mm/hr":
            raise ValueError(
                f"Unexpected units: {precipitation_var.units}"
            )

        if precipitation_var.dimensions != (
            "time", "lon", "lat"
        ):
            raise ValueError(
                f"Unexpected dimensions: "
                f"{precipitation_var.dimensions}"
            )

        raw = np.ma.asarray(
            precipitation_var[0, :, :],
            dtype=np.float64
        )

        # Source is (lon, lat).
        # Convert to (lat, lon) for our output.

        rainfall = raw.T

        data = rainfall.filled(np.nan)

        valid = (
            ~np.ma.getmaskarray(rainfall)
            & np.isfinite(data)
        )

        if np.any(data[valid] < 0):
            raise ValueError(
                "Negative valid precipitation values found."
            )

        records.append({
            "start": start,
            "end": end,
            "data": data,
            "valid": valid
        })


# ==========================================
# 3. SORT AND VERIFY TEMPORAL COVERAGE
# ==========================================

records.sort(
    key=lambda record: record["start"]
)

expected_times = [
    EXPECTED_START + timedelta(minutes=30 * i)
    for i in range(EXPECTED_INTERVALS)
]

actual_times = [
    record["start"]
    for record in records
]

print("\n========== TEMPORAL VALIDATION ==========")

if actual_times != expected_times:
    raise RuntimeError(
        "Missing, duplicated or unexpected timestamps."
    )

for record in records:

    if record["end"] != (
        record["start"] + timedelta(minutes=30)
    ):
        raise RuntimeError(
            "Invalid temporal bounds."
        )

print("Chronological order: correct")
print("Missing intervals: 0")
print("Duplicate intervals: 0")
print("Verified intervals:", len(records))


# ==========================================
# 4. ACCUMULATE RAINFALL
# ==========================================

print("\n========== AGGREGATION ==========")

shape = records[0]["data"].shape

rainfall_sum = np.zeros(
    shape,
    dtype=np.float64
)

valid_count = np.zeros(
    shape,
    dtype=np.uint8
)

for record in records:

    data = record["data"]
    valid = record["valid"]

    # mm/hr * 0.5 hours = mm per interval

    rainfall_sum += np.where(
        valid,
        data * INTERVAL_HOURS,
        0.0
    )

    valid_count += valid.astype(np.uint8)


# A pixel is complete only if all 24
# half-hour observations are available.

complete = valid_count == EXPECTED_INTERVALS

rainfall_12h = np.where(
    complete,
    rainfall_sum,
    np.nan
)

valid_pixels = int(
    np.count_nonzero(complete)
)

incomplete_pixels = int(
    complete.size - valid_pixels
)

print("Spatial dimensions:", rainfall_12h.shape)
print("Complete pixels:", valid_pixels)
print("Incomplete pixels:", incomplete_pixels)


# ==========================================
# 5. CALCULATE SUMMARY STATISTICS
# ==========================================

valid_values = rainfall_12h[
    np.isfinite(rainfall_12h)
]

if valid_values.size == 0:
    raise RuntimeError(
        "No complete rainfall pixels available."
    )

minimum = float(valid_values.min())
maximum = float(valid_values.max())
mean = float(valid_values.mean())

print("\n========== RAINFALL STATISTICS ==========")

print(f"Minimum: {minimum:.4f} mm")
print(f"Maximum: {maximum:.4f} mm")
print(f"Mean: {mean:.4f} mm")


# ==========================================
# 6. SAVE NETCDF OUTPUT
# ==========================================

print("\n========== SAVING FRAME ==========")

with Dataset(
    OUTPUT_FILE,
    "w",
    format="NETCDF4"
) as out:

    # Dimensions

    out.createDimension("time", 1)
    out.createDimension("lat", len(reference_lat))
    out.createDimension("lon", len(reference_lon))
    out.createDimension("nv", 2)

    # Coordinates

    lat_var = out.createVariable(
        "lat",
        "f4",
        ("lat",)
    )

    lon_var = out.createVariable(
        "lon",
        "f4",
        ("lon",)
    )

    lat_var.units = "degrees_north"
    lon_var.units = "degrees_east"

    lat_var[:] = reference_lat
    lon_var[:] = reference_lon

    # Time

    time_var = out.createVariable(
        "time",
        "f8",
        ("time",)
    )

    time_var.units = (
        "seconds since 1970-01-01 00:00:00 UTC"
    )

    time_var.calendar = "standard"
    time_var.bounds = "time_bounds"

    start = records[0]["start"]
    end = records[-1]["end"]

    time_var[0] = start.timestamp()

    time_bounds = out.createVariable(
        "time_bounds",
        "f8",
        ("time", "nv")
    )

    time_bounds.units = time_var.units
    time_bounds.calendar = "standard"

    time_bounds[0, :] = [
        start.timestamp(),
        end.timestamp()
    ]

    # Accumulated precipitation

    precipitation = out.createVariable(
        "precipitation_12h",
        "f4",
        ("time", "lat", "lon"),
        zlib=True,
        complevel=4,
        fill_value=np.float32(-9999.9)
    )

    precipitation.units = "mm"
    precipitation.long_name = (
        "Accumulated precipitation over 12 hours"
    )

    precipitation.coordinates = "time lat lon"

    precipitation[0, :, :] = (
        np.ma.masked_invalid(rainfall_12h)
    )

    # Valid observation count per pixel

    count_var = out.createVariable(
        "valid_interval_count",
        "u1",
        ("lat", "lon")
    )

    count_var.units = "intervals"
    count_var.long_name = (
        "Number of valid half-hourly observations"
    )

    count_var[:, :] = valid_count

    # Global metadata

    out.title = (
        "Earth Detective - IMERG 12-hour rainfall frame"
    )

    out.source_product = "GPM_3IMERGHH"
    out.source_version = "V07"
    out.source_variable = "Grid/precipitation"
    out.source_units = "mm/hr"

    out.temporal_aggregation = (
        "Sum of 24 half-hourly rates multiplied by 0.5 hours"
    )

    out.time_coverage_start = start.isoformat()
    out.time_coverage_end = end.isoformat()

    out.number_of_source_granules = EXPECTED_INTERVALS

    out.native_spatial_resolution = (
        "0.1 degree; no 5 km resampling performed"
    )

print("Output saved:", OUTPUT_FILE)


# ==========================================
# 7. FINAL REPORT
# ==========================================

print("\n========== FINAL REPORT ==========")

print("Status: SUCCESS")
print("Source granules:", EXPECTED_INTERVALS)
print("Frame start:", records[0]["start"])
print("Frame end:", records[-1]["end"])
print("Spatial shape:", rainfall_12h.shape)
print("Complete pixels:", valid_pixels)
print("Incomplete pixels:", incomplete_pixels)

print(f"Minimum rainfall: {minimum:.4f} mm")
print(f"Maximum rainfall: {maximum:.4f} mm")
print(f"Mean rainfall: {mean:.4f} mm")

print("\nFirst 12-hour rainfall frame created!")
