import json
import re
from pathlib import Path

import earthaccess

BBOX = (66.0, 23.5, 71.5, 28.5)

PRODUCTS = [
    "NASADEM_HGT",
    "NASADEM_SC"
]

output = Path(
    "data/processed/metadata/nasadem_sindh_catalog.json"
)

earthaccess.login(
    strategy="interactive",
    persist=True
)

catalog = {
    "region": "Sindh study window, Pakistan",
    "bbox": BBOX,
    "version": "001",
    "products": {}
}

for product in PRODUCTS:

    print("\n" + "=" * 50)
    print("SEARCHING:", product)
    print("=" * 50)

    granules = earthaccess.search_data(
        short_name=product,
        version="001",
        cloud_hosted=True,
        bounding_box=BBOX,
        count=-1
    )

    print("Granules found:", len(granules))

    if not granules:
        raise RuntimeError(
            "No NASA granules found for " + product
        )

    records = []

    for granule in granules:

        name = granule["umm"]["GranuleUR"]

        match = re.search(
            r"([ns]\d{2}[ew]\d{3})",
            name.lower()
        )

        tile_id = match.group(1) if match else None

        records.append({
            "name": name,
            "tile_id": tile_id
        })

    records.sort(
        key=lambda item: item["name"]
    )

    tile_ids = {
        item["tile_id"]
        for item in records
        if item["tile_id"]
    }

    print("Unique tile IDs:", len(tile_ids))

    print("\nFirst 10 granules:")

    for item in records[:10]:
        print(" ", item["name"])

    print("\nSample download links:")

    try:
        for link in granules[0].data_links(
            access="external"
        )[:3]:
            print(link)
    except Exception as exc:
        print("Links not exposed:", exc)

    catalog["products"][product] = {
        "granule_count": len(records),
        "tile_ids": sorted(tile_ids),
        "granules": records
    }

hgt_tiles = set(
    catalog["products"]["NASADEM_HGT"]["tile_ids"]
)

slope_tiles = set(
    catalog["products"]["NASADEM_SC"]["tile_ids"]
)

print("\n========== COVERAGE COMPARISON ==========")

print("Elevation tiles:", len(hgt_tiles))
print("Slope tiles:", len(slope_tiles))
print("Matching tile IDs:", len(hgt_tiles & slope_tiles))
print("Only in elevation:", sorted(hgt_tiles - slope_tiles))
print("Only in slope:", sorted(slope_tiles - hgt_tiles))

output.parent.mkdir(
    parents=True,
    exist_ok=True
)

output.write_text(
    json.dumps(catalog, indent=2),
    encoding="utf-8"
)

print("\nCatalog saved:", output)
print("No terrain files downloaded.")