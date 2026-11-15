
from pathlib import Path
import geopandas as gpd

path = Path(
    "data/processed/grids/"
    "sindh_study_window_grid_5km.geojson"
)

grid = gpd.read_file(path)

print("GRID VALIDATION")
print("---------------------------")

print("Total cells:", len(grid))
print("Unique IDs:", grid["cell_id"].nunique())
print("CRS:", grid.crs)
print("Invalid geometries:", (~grid.geometry.is_valid).sum())
print("Empty geometries:", grid.geometry.is_empty.sum())

print(
    "Minimum coverage:",
    round(grid["coverage_ratio"].min(), 4)
)

print(
    "Maximum coverage:",
    round(grid["coverage_ratio"].max(), 4)
)

print(
    "Average clipped area:",
    round(grid["clipped_area_km2"].mean(), 3),
    "km²"
)

assert len(grid) == 12412
assert grid["cell_id"].is_unique
assert grid.crs.to_epsg() == 4326
assert grid.geometry.is_valid.all()
assert not grid.geometry.is_empty.any()

print("\nAll basic grid checks passed!")
