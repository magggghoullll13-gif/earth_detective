import json
import zipfile
from pathlib import Path

import earthaccess

TILE = "n24e067"
BBOX = (66.0, 23.5, 71.5, 28.5)

ROOT = Path("data/raw/pakistan/nasadem")
REPORT = Path(
    "data/processed/metadata/"
    "nasadem_sample_inspection.json"
)

earthaccess.login(
    strategy="interactive",
    persist=True
)

report = {
    "tile": TILE,
    "products": {}
}

for product in ["NASADEM_HGT", "NASADEM_SC"]:

    print("\n" + "=" * 50)
    print("PRODUCT:", product)
    print("TILE:", TILE)
    print("=" * 50)

    granules = earthaccess.search_data(
        short_name=product,
        version="001",
        cloud_hosted=True,
        bounding_box=BBOX,
        count=-1
    )

    matches = [
        g for g in granules
        if g["umm"]["GranuleUR"].lower()
        == f"{product}_{TILE}".lower()
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected 1 matching granule for "
            f"{product}, found {len(matches)}"
        )

    folder = ROOT / product / "sample"
    folder.mkdir(parents=True, exist_ok=True)

    print("\nDownloading sample ZIP...")

    files = earthaccess.download(
        matches,
        local_path=str(folder),
        threads=1,
        show_progress=True
    )

    if len(files) != 1:
        raise RuntimeError(
            f"Expected one downloaded file for {product}"
        )

    file_path = Path(files[0])

    if not file_path.exists():
        raise FileNotFoundError(file_path)

    if not zipfile.is_zipfile(file_path):
        raise RuntimeError(
            f"Downloaded file is not a valid ZIP: {file_path}"
        )

    print("\nDownloaded:", file_path)
    print("ZIP size MB:", round(
        file_path.stat().st_size / 1048576, 2
    ))

    with zipfile.ZipFile(file_path) as archive:

        members = [
            {
                "name": info.filename,
                "size_mb": round(
                    info.file_size / 1048576, 3
                ),
                "compressed_mb": round(
                    info.compress_size / 1048576, 3
                )
            }
            for info in archive.infolist()
            if not info.is_dir()
        ]

        print("\n========== ZIP CONTENTS ==========")

        for item in members:
            print(
                item["name"],
                "| uncompressed:",
                item["size_mb"],
                "MB"
            )

        if not members:
            raise RuntimeError(
                f"ZIP archive contains no files: {file_path}"
            )

    report["products"][product] = {
        "archive": str(file_path),
        "archive_size_bytes": file_path.stat().st_size,
        "members": members
    }

REPORT.parent.mkdir(parents=True, exist_ok=True)

REPORT.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print("\n========== SAMPLE INSPECTION COMPLETE ==========")
print("Tile:", TILE)
print("Products inspected:", len(report["products"]))
print("Report:", REPORT)
print("No full-region terrain download performed.")