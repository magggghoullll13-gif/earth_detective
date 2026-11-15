
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, num2date

FILE = Path(
    "data/processed/rainfall_frames/"
    "imerg_2022-08-01_00-12_utc.nc"
)

print("EARTH DETECTIVE - FRAME VALIDATION")

with Dataset(FILE, "r") as ds:

    # 1. Coordinates
    lat = ds.variables["lat"][:]
    lon = ds.variables["lon"][:]

    # 2. Precipitation
    rain_var = ds.variables["precipitation_12h"]
    rain = np.ma.asarray(rain_var[:])

    values = rain.compressed()

    # 3. Temporal coverage
    time_var = ds.variables["time"]
    bounds_var = ds.variables["time_bounds"]

    bounds = num2date(
        bounds_var[:],
        units=time_var.units,
        calendar=time_var.calendar
    )

    # 4. Valid interval counts
    counts = ds.variables[
        "valid_interval_count"
    ][:]

    # 5. Assertions
    assert rain.shape == (1, 50, 56)
    assert len(lat) == 50
    assert len(lon) == 56

    assert np.all(np.diff(lat) > 0)
    assert np.all(np.diff(lon) > 0)

    assert np.allclose(np.diff(lat), 0.1, atol=0.001)
    assert np.allclose(np.diff(lon), 0.1, atol=0.001)

    assert rain_var.units == "mm"
    assert np.all(counts == 24)

    assert len(values) == 2800
    assert np.all(values >= 0)

    assert np.isclose(values.min(), 0.0)
    assert np.isclose(values.max(), 9.415, atol=0.001)
    assert np.isclose(values.mean(), 0.215, atol=0.001)

    print("\n========== VALIDATION RESULTS ==========")

    print("Dimensions:", rain.shape)
    print("Latitude range:", lat.min(), lat.max())
    print("Longitude range:", lon.min(), lon.max())

    print("Rainfall units:", rain_var.units)

    print("Time start:", bounds[0, 0])
    print("Time end:", bounds[0, 1])

    print("Complete pixels:", len(values))
    print("Minimum:", values.min())
    print("Maximum:", values.max())
    print("Mean:", values.mean())

    print("Valid observations per pixel:")
    print("Minimum:", counts.min())
    print("Maximum:", counts.max())

    print("\nSUCCESS: All validation checks passed!")
