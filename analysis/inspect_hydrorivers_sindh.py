import json
from pathlib import Path

import geopandas as gpd
import pyogrio
from pyproj import CRS
from shapely.geometry import box

# ==========================================
# EARTH DETECTIVE - HYDRORIVERS SUBSET
# ==========================================

ARCHIVE = Path(
    "data/raw/hydrology/hydrorivers/"
    "HydroRIVERS_v10_as_shp.zip"
)

OUTPUT = Path(
    "data/processed/hydrology/"
    "hydrorivers_sindh_buffered.gpkg"
)

REPORT = Path(
    "data/processed/metadata/"
    "hydrorivers_sindh_subset_report.json"
)

# Original Earth Detective study window
STUDY = (66.0, 23.5, 71.5, 28.5)

# Wider area for nearest-river calculations
BUFFERED = (65.0, 22.5, 72.5, 29.5)

if not ARCHIVE.is_file():
    raise FileNotFoundError(ARCHIVE)

# Read the shapefile directly from the ZIP archive.
# No complete Asia shapefile extraction required.

uri = (
    "zip://" + ARCHIVE.resolve().as_posix()
    + "!HydroRIVERS_v10_as_shp/"
    + "HydroRIVERS_v10_as.shp"
)

print("\n========== SOURCE INSPECTION ==========")

info = pyogrio.read_info(uri)

source_crs = CRS.from_user_input(info["crs"])

print("Source CRS:", source_crs.to_string())
print("Geometry type:", info["geometry_type"])
print("Source feature count:", info["features"])

if source_crs.to_epsg() != 4326:
    raise RuntimeError(
        "Expected geographic EPSG:4326. "
        "Check CRS before applying the longitude/latitude bbox."
    )

print("\n========== READING REGIONAL RIVERS ==========")

rivers = gpd.read_file(
    uri,
    bbox=BUFFERED,
    engine="pyogrio"
)

print("Features returned by spatial filter:", len(rivers))

if rivers.empty:
    raise RuntimeError(
        "No river segments were found near the study area."
    )

rivers = rivers.loc[
    rivers.geometry.notna()
    & ~rivers.geometry.is_empty
].copy()

# Clip line geometries to the buffered region,
# avoiding oversized geometry in our local subset.

buffer_polygon = box(*BUFFERED)

rivers["geometry"] = rivers.geometry.intersection(
    buffer_polygon
)

rivers = rivers.loc[
    rivers.geometry.geom_type.isin([
        "LineString",
        "MultiLineString"
    ])
    & ~rivers.geometry.is_empty
].copy()

rivers = rivers.loc[
    rivers.geometry.length > 0
].copy()

print("Usable river geometries:", len(rivers))

if rivers.empty:
    raise RuntimeError("No usable line geometries remain.")

print("\n========== ATTRIBUTE COLUMNS ==========")

for column in rivers.columns:
    print(column)

required = [
    "HYRIV_ID",
    "ORD_STRA",
    "LENGTH_KM",
    "DIS_AV_CMS"
]

missing = [
    name for name in required
    if name not in rivers.columns
]

if missing:
    raise RuntimeError(
        f"Missing expected HydroRIVERS fields: {missing}"
    )

print("\n========== DATA QUALITY ==========")

invalid = int((~rivers.geometry.is_valid).sum())
empty = int(rivers.geometry.is_empty.sum())

print("Invalid geometries:", invalid)
print("Empty geometries:", empty)
print("Unique river IDs:", rivers["HYRIV_ID"].nunique())

print(
    "River segments intersecting study window:",
    int(rivers.intersects(box(*STUDY)).sum())
)

print("\n========== SAMPLE RIVER ATTRIBUTES ==========")

sample_columns = [
    column for column in [
        "HYRIV_ID",
        "LENGTH_KM",
        "ORD_STRA",
        "ORD_CLAS",
        "DIS_AV_CMS",
        "NEXT_DOWN"
    ]
    if column in rivers.columns
]

print(
    rivers[sample_columns]
    .head(5)
    .to_string(index=False)
)

# Store a compact regional GeoPackage locally.
# Original LENGTH_KM describes the source segment,
# not its length after clipping.

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

if OUTPUT.exists():
    OUTPUT.unlink()

rivers.to_file(
    OUTPUT,
    layer="hydrorivers_sindh_buffered",
    driver="GPKG",
    index=False
)

sample_records = json.loads(
    rivers[sample_columns]
    .head(5)
    .to_json(orient="records")
)

report = {
    "dataset": "HydroRIVERS v1.0",
    "publisher": "HydroSHEDS",
    "source_crs": source_crs.to_string(),
    "study_bbox": list(STUDY),
    "buffered_bbox": list(BUFFERED),
    "source_feature_count": int(info["features"]),
    "regional_feature_count": int(len(rivers)),
    "unique_river_ids": int(
        rivers["HYRIV_ID"].nunique()
    ),
    "segments_in_study_window": int(
        rivers.intersects(box(*STUDY)).sum()
    ),
    "columns": list(rivers.columns),
    "invalid_geometries": invalid,
    "empty_geometries": empty,
    "sample_records": sample_records,
    "local_subset": str(OUTPUT),
    "status": "regional_subset_created",
    "notes": [
        "Study area is a rectangle, not a province boundary.",
        "Buffer includes rivers outside the study area.",
        "LENGTH_KM describes the original source segment.",
        "No river proximity or flood score calculated yet.",
        "Dataset is HydroSHEDS, not directly NASA."
    ]
}

REPORT.parent.mkdir(parents=True, exist_ok=True)

REPORT.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print("\n========== HYDRORIVERS SUBSET COMPLETE ==========")
print("Regional river features:", len(rivers))
print("Unique river IDs:", rivers["HYRIV_ID"].nunique())
print("Output:", OUTPUT)
print("Report:", REPORT)
print("Ready for Universal Grid integration.")