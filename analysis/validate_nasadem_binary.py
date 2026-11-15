import json
import zipfile
from pathlib import Path

import numpy as np

TILE = "n24e067"
SIZE = 3601

root = Path("data/raw/pakistan/nasadem")

hgt_zip = root / "NASADEM_HGT" / "sample" / f"NASADEM_HGT_{TILE}.zip"
sc_zip = root / "NASADEM_SC" / "sample" / f"NASADEM_SC_{TILE}.zip"

def read(archive_path, extension, dtype):
    with zipfile.ZipFile(archive_path) as archive:
        raw = archive.read(f"{TILE}.{extension}")

    array = np.frombuffer(raw, dtype=dtype)

    assert array.size == SIZE * SIZE, (
        f"Unexpected raster dimensions: {extension}"
    )

    return array.reshape(SIZE, SIZE)

print("\n========== NASADEM BINARY VALIDATION ==========")

# NASADEM binary rasters are big-endian.
elevation = read(hgt_zip, "hgt", ">i2")
slope_raw = read(sc_zip, "slope", ">u2")

water_hgt = read(hgt_zip, "swb", "u1")
water_sc = read(sc_zip, "swb", "u1")

land = water_hgt == 0
water = water_hgt == 255

valid_elevation = land & (elevation >= -32767)
valid_slope = land & (slope_raw <= 9000)

elev = elevation[valid_elevation]
slope = slope_raw[valid_slope].astype(np.float32) / 100

assert elev.size > 0
assert slope.size > 0

print("\n[1] ELEVATION")
print("Minimum:", int(elev.min()), "m")
print("Maximum:", int(elev.max()), "m")
print("Mean:", round(float(elev.mean()), 3), "m")
print("Median:", float(np.median(elev)), "m")

print("\n[2] SLOPE")
print("Minimum:", float(slope.min()), "degrees")
print("Maximum:", float(slope.max()), "degrees")
print("Mean:", round(float(slope.mean()), 3), "degrees")
print("Median:", round(float(np.median(slope)), 3))
print("95th percentile:", round(float(np.percentile(slope, 95)), 3))

print("\n[3] WATER MASK")
print("Land samples:", int(land.sum()))
print("Water samples:", int(water.sum()))
print("Unexpected mask codes:", int((~(land | water)).sum()))
print("HGT/SC mask differences:", int((water_hgt != water_sc).sum()))

print("\n[4] QUALITY CHECK")
print("Raw slope above 90 degrees:",
      int((land & (slope_raw > 9000)).sum()))
print("Land with zero slope:",
      int((land & (slope_raw == 0)).sum()))

report = {
    "tile": TILE,
    "raster_shape": [SIZE, SIZE],
    "elevation": {
        "units": "m above EGM96",
        "min": int(elev.min()),
        "max": int(elev.max()),
        "mean": float(elev.mean())
    },
    "slope": {
        "units": "degrees",
        "min": float(slope.min()),
        "max": float(slope.max()),
        "mean": float(slope.mean()),
        "p95": float(np.percentile(slope, 95))
    },
    "quality": {
        "land_count": int(land.sum()),
        "water_count": int(water.sum()),
        "mask_differences": int((water_hgt != water_sc).sum()),
        "land_slope_over_90": int(
            (land & (slope_raw > 9000)).sum()
        )
    }
}

output = Path(
    "data/processed/metadata/nasadem_binary_validation.json"
)

output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2), encoding="utf-8")

print("\n========== VALIDATION COMPLETED ==========")
print("Report:", output)