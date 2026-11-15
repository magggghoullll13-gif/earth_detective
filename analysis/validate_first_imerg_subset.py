
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, num2date

FILE = Path(
    "data/raw/pakistan/imerg_half_hourly/test/"
    "464744101_GPM_3IMERGHH.07_"
    "3B-HHR.MS.MRG.3IMERG."
    "20220801-S000000-E002959.0000.V07B_"
    "Grid_precipitation_subsetted.nc4"
)

print("EARTH DETECTIVE - SPATIAL DATA VALIDATION")

with Dataset(FILE, "r") as ds:

    grid = ds.groups["Grid"]

    # 1. Coordinates
    lat = np.asarray(grid.variables["lat"][:])
    lon = np.asarray(grid.variables["lon"][:])

    print("\n========== COORDINATES ==========")

    print("Latitude count:", len(lat))
    print("Longitude count:", len(lon))

    print("Latitude range:", lat.min(), "to", lat.max())
    print("Longitude range:", lon.min(), "to", lon.max())

    print("First 5 latitudes:", lat[:5])
    print("First 5 longitudes:", lon[:5])

    print("Latitude spacing:", np.median(np.diff(lat)))
    print("Longitude spacing:", np.median(np.diff(lon)))

    print("Latitude ascending:", np.all(np.diff(lat) > 0))
    print("Longitude ascending:", np.all(np.diff(lon) > 0))

    # 2. Coordinate boundaries
    print("\n========== COORDINATE BOUNDS ==========")

    for name in ["lat_bnds", "lon_bnds"]:
        if name in grid.variables:
            bounds = np.asarray(grid.variables[name][:])
            print(name, "shape:", bounds.shape)
            print(name, "minimum:", bounds.min())
            print(name, "maximum:", bounds.max())

    # 3. Time validation
    print("\n========== TIME ==========")

    time_var = grid.variables["time"]
    time_bounds = grid.variables["time_bnds"]

    print("Time units:", time_var.units)

    decoded = num2date(
        time_bounds[:],
        units=time_var.units,
        calendar=getattr(time_var, "calendar", "standard")
    )

    print("Time bounds:", decoded)

    # 4. Precipitation
    print("\n========== PRECIPITATION ==========")

    variable = grid.variables["precipitation"]

    print("Dimensions:", variable.dimensions)
    print("Shape:", variable.shape)
    print("Units:", variable.units)

    for attr in variable.ncattrs():
        print(f"{attr}: {variable.getncattr(attr)}")

    rainfall = np.ma.masked_invalid(variable[:])

    values = rainfall.compressed()
    values = values[np.isfinite(values)]

    print("\nValid measurements:", len(values))
    print("Missing measurements:", rainfall.size - len(values))

    if len(values) > 0:
        print("Minimum:", values.min(), "mm/hr")
        print("Maximum:", values.max(), "mm/hr")
        print("Mean:", values.mean(), "mm/hr")
        print("Median:", np.median(values), "mm/hr")
        print("Zero measurements:", np.sum(values == 0))
        print("Negative measurements:", np.sum(values < 0))

    # 5. Sample values
    print("\n========== SAMPLE DATA ==========")

    print("First 5 x 5 rainfall measurements:")

    print(rainfall[0, :5, :5])

    print("\nValidation script completed.")
