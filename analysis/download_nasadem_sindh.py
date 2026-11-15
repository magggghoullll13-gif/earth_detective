import json
import shutil
import zipfile
from pathlib import Path

import earthaccess

# ==============================================
# EARTH DETECTIVE: NASADEM REGIONAL DOWNLOAD
# ==============================================

BBOX = (66.0, 23.5, 71.5, 28.5)

PRODUCTS = ["NASADEM_HGT", "NASADEM_SC"]

ROOT = Path("data/raw/pakistan/nasadem")
CATALOG = Path(
    "data/processed/metadata/nasadem_sindh_catalog.json"
)
REPORT = Path(
    "data/processed/metadata/nasadem_download_progress.json"
)

with CATALOG.open(encoding="utf-8") as f:
    catalog = json.load(f)

hgt_ids = set(catalog["products"]["NASADEM_HGT"]["tile_ids"])
sc_ids = set(catalog["products"]["NASADEM_SC"]["tile_ids"])

assert hgt_ids == sc_ids, "Tile coverage mismatch"
assert len(hgt_ids) == 39, "Unexpected tile count"

tiles = sorted(hgt_ids)

free_gb = shutil.disk_usage(Path.cwd()).free / 1024**3
print(f"Available disk space: {free_gb:.2f} GiB")

if free_gb < 5:
    print(
        "WARNING: Less than 5 GiB free. "
        "The complete download may not fit."
    )

earthaccess.login(
    strategy="interactive",
    persist=True
)

progress = {
    "region": "Sindh study window, Pakistan",
    "bbox": list(BBOX),
    "tile_count": len(tiles),
    "products": {},
    "status": "in_progress"
}

def archive_valid(path, expected_member):
    if not path.is_file() or path.stat().st_size == 0:
        return False

    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if expected_member not in names:
                return False
            return archive.testzip() is None
    except (zipfile.BadZipFile, OSError):
        return False


def write_report():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temp = REPORT.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(progress, indent=2),
        encoding="utf-8"
    )
    temp.replace(REPORT)


all_failures = []

for product in PRODUCTS:
    print("\n" + "=" * 60)
    print("PRODUCT:", product)
    print("=" * 60)

    result = earthaccess.search_data(
        short_name=product,
        version="001",
        cloud_hosted=True,
        bounding_box=BBOX,
        count=-1
    )

    by_name = {
        g["umm"]["GranuleUR"].lower(): g
        for g in result
    }

    target_dir = ROOT / product
    target_dir.mkdir(parents=True, exist_ok=True)

    product_records = []
    progress["products"][product] = product_records

    extension = "hgt" if product == "NASADEM_HGT" else "slope"

    for index, tile in enumerate(tiles, start=1):
        name = f"{product}_{tile}"
        target = target_dir / f"{name}.zip"
        sample = target_dir / "sample" / f"{name}.zip"
        member = f"{tile}.{extension}"

        print(f"\n[{index}/{len(tiles)}] {name}")

        status = "pending"

        # Reuse the sample already downloaded.
        if not target.exists() and sample.exists():
            if archive_valid(sample, member):
                shutil.copy2(sample, target)
                print("Reused validated sample archive.")

        if archive_valid(target, member):
            status = "complete"
            print("Archive already present and valid.")
        else:
            if target.exists():
                target.unlink()

            granule = by_name.get(name.lower())

            if granule is None:
                print("ERROR: Granule not found in NASA search.")
                status = "missing_granule"
            else:
                for attempt in range(1, 4):
                    try:
                        print(f"Downloading (attempt {attempt}/3)...")

                        earthaccess.download(
                            [granule],
                            local_path=str(target_dir),
                            threads=1,
                            show_progress=True
                        )

                        if not archive_valid(target, member):
                            raise RuntimeError(
                                "Downloaded ZIP failed integrity check."
                            )

                        status = "complete"
                        print("Download verified.")
                        break

                    except Exception as exc:
                        print(f"Attempt failed: {exc}")

                        if target.exists():
                            target.unlink()

                        status = "failed"

        if status != "complete":
            all_failures.append(name)

        item = {
            "tile_id": tile,
            "granule": name,
            "status": status,
            "path": str(target),
            "size_bytes": (
                target.stat().st_size
                if target.exists() else None
            )
        }

        product_records.append(item)
        write_report()

    completed = sum(
        r["status"] == "complete"
        for r in product_records
    )

    print(
        f"\n{product}: {completed}/{len(tiles)} "
        "validated archives"
    )

progress["status"] = (
    "complete" if not all_failures else "incomplete"
)

write_report()

print("\n========== NASADEM DOWNLOAD SUMMARY ==========")

for product, records in progress["products"].items():
    completed = sum(r["status"] == "complete" for r in records)

    total_bytes = sum(
        r["size_bytes"] or 0
        for r in records
    )

    print(
        f"{product}: {completed}/{len(tiles)} tiles, "
        f"{total_bytes / 1024**3:.3f} GiB"
    )

print("Failed granules:", len(all_failures))
print("Report:", REPORT)
print("Status:", progress["status"])

if all_failures:
    print("Retry by running this script again.")
    raise SystemExit(1)

print("\nALL 78 NASADEM ARCHIVES VALIDATED.")