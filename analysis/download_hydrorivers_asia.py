import json
import zipfile
from pathlib import Path
import requests

URL = (
    "https://data.hydrosheds.org/file/HydroRIVERS/"
    "HydroRIVERS_v10_as_shp.zip"
)

FOLDER = Path("data/raw/hydrology/hydrorivers")
FOLDER.mkdir(parents=True, exist_ok=True)

TARGET = FOLDER / "HydroRIVERS_v10_as_shp.zip"

REPORT = Path(
    "data/processed/metadata/"
    "hydrorivers_asia_inspection.json"
)

def valid_zip(path):
    if not path.exists():
        return False
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None
    except (zipfile.BadZipFile, OSError):
        return False

print("\n========== HYDRORIVERS ASIA ==========")

if valid_zip(TARGET):
    print("Existing archive is valid. Skipping download.")
else:
    temp = TARGET.with_suffix(".zip.part")

    if temp.exists():
        temp.unlink()

    print("Downloading official HydroRIVERS Asia dataset...")

    with requests.get(
        URL, stream=True, timeout=(30, 180)
    ) as response:
        response.raise_for_status()

        with temp.open("wb") as file:
            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    file.write(chunk)

    if not valid_zip(temp):
        raise RuntimeError("HydroRIVERS ZIP validation failed.")

    temp.replace(TARGET)

print("Archive:", TARGET)
print("Size MiB:", round(TARGET.stat().st_size / 1048576, 2))

with zipfile.ZipFile(TARGET) as archive:
    files = [
        {
            "name": item.filename,
            "bytes": item.file_size
        }
        for item in archive.infolist()
        if not item.is_dir()
    ]

print("\n========== SHAPEFILE CONTENTS ==========")

for item in files:
    print(item["name"])

shapefiles = [
    item["name"]
    for item in files
    if item["name"].lower().endswith(".shp")
]

if not shapefiles:
    raise RuntimeError("No shapefile found in archive.")

report = {
    "dataset": "HydroRIVERS version 1",
    "region": "Asia",
    "source_url": URL,
    "archive_path": str(TARGET),
    "archive_size_bytes": TARGET.stat().st_size,
    "shapefiles": shapefiles,
    "members": files,
    "status": "archive_validated",
    "note": "Non-NASA hydrography; inspect license before redistribution."
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print("\n========== DOWNLOAD COMPLETED ==========")
print("Valid shapefiles:", len(shapefiles))
print("Report:", REPORT)