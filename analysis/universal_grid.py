
from pathlib import Path
import argparse
import json
import math

import geopandas as gpd
from shapely.geometry import box
from shapely.ops import unary_union


# =========================================
# EARTH DETECTIVE - UNIVERSAL GRID V1
# =========================================

GRID_SIZE_M = 5000

# Global equal-area projection
GRID_CRS = "EPSG:6933"

# Geographic output projection
OUTPUT_CRS = "EPSG:4326"

GRID_ORIGIN_X = 0
GRID_ORIGIN_Y = 0


def make_cell_id(row, col):
    """Generate a stable ID from grid coordinates."""
    return f"r{row}_c{col}"


def load_region(boundary_path=None, bbox=None):
    """Load a polygon or create a rectangular study boundary."""

    if boundary_path:
        region = gpd.read_file(boundary_path)

        if region.empty:
            raise ValueError("Boundary file is empty.")

        if region.crs is None:
            raise ValueError(
                "Boundary has no CRS. Define its CRS first."
            )

        geometry = unary_union(region.geometry)

    elif bbox:
        west, south, east, north = bbox

        if west >= east or south >= north:
            raise ValueError("Invalid bounding box.")

        boundary = box(west, south, east, north)

        region = gpd.GeoDataFrame(
            {"name": ["Study area"]},
            geometry=[boundary],
            crs=OUTPUT_CRS
        )

        geometry = boundary

    else:
        raise ValueError(
            "Provide a boundary GeoJSON or bounding box."
        )

    if geometry.is_empty:
        raise ValueError("Region geometry is empty.")

    if not geometry.is_valid:
        geometry = geometry.buffer(0)

    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("Could not repair region geometry.")

    return gpd.GeoDataFrame(
        {"region": ["study_area"]},
        geometry=[geometry],
        crs=region.crs if boundary_path else OUTPUT_CRS
    )


def generate_grid(region, cell_size=GRID_SIZE_M):
    """Generate a fixed, globally aligned projected grid."""

    if cell_size <= 0:
        raise ValueError("Cell size must be positive.")

    # Project region into meters
    projected = region.to_crs(GRID_CRS)

    region_geometry = unary_union(projected.geometry)

    min_x, min_y, max_x, max_y = (
        region_geometry.bounds
    )

    # Calculate grid row/column ranges
    min_col = math.floor(
        (min_x - GRID_ORIGIN_X) / cell_size
    )

    max_col = math.ceil(
        (max_x - GRID_ORIGIN_X) / cell_size
    )

    min_row = math.floor(
        (min_y - GRID_ORIGIN_Y) / cell_size
    )

    max_row = math.ceil(
        (max_y - GRID_ORIGIN_Y) / cell_size
    )

    cells = []

    for row in range(min_row, max_row):

        for col in range(min_col, max_col):

            x1 = GRID_ORIGIN_X + col * cell_size
            y1 = GRID_ORIGIN_Y + row * cell_size

            x2 = x1 + cell_size
            y2 = y1 + cell_size

            full_cell = box(x1, y1, x2, y2)

            # Clip cell to selected region
            clipped = full_cell.intersection(
                region_geometry
            )

            if clipped.is_empty:
                continue

            if clipped.area <= 0:
                continue

            cells.append({
                "cell_id": make_cell_id(row, col),
                "row": row,
                "col": col,
                "full_area_km2": (
                    full_cell.area / 1_000_000
                ),
                "clipped_area_km2": (
                    clipped.area / 1_000_000
                ),
                "coverage_ratio": (
                    clipped.area / full_cell.area
                ),
                "geometry": clipped
            })

    if not cells:
        raise ValueError("No grid cells generated.")

    return cells


def add_neighbors(cells):
    """Find cells sharing edges and cells touching corners."""

    lookup = {
        (cell["row"], cell["col"]): cell
        for cell in cells
    }

    # Edge-sharing neighbors
    edge_directions = [
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1)
    ]

    # All eight directions
    all_directions = [
        (dr, dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
        if dr != 0 or dc != 0
    ]

    for cell in cells:

        row = cell["row"]
        col = cell["col"]

        edge_neighbors = []
        all_neighbors = []

        for dr, dc in edge_directions:

            neighbor = lookup.get(
                (row + dr, col + dc)
            )

            if neighbor:
                edge_neighbors.append(
                    neighbor["cell_id"]
                )

        for dr, dc in all_directions:

            neighbor = lookup.get(
                (row + dr, col + dc)
            )

            if neighbor:
                all_neighbors.append(
                    neighbor["cell_id"]
                )

        cell["neighbors_4"] = edge_neighbors
        cell["neighbors_8"] = all_neighbors

    return cells


def export_grid(
    cells,
    output_dir,
    region_name,
    cell_size
):
    """Export grid geometry and metadata."""

    output_dir = Path(output_dir)
    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    records = []

    for cell in cells:

        centroid = cell["geometry"].centroid

        records.append({
            "cell_id": cell["cell_id"],
            "row": cell["row"],
            "col": cell["col"],
            "cell_size_m": cell_size,
            "full_area_km2": cell["full_area_km2"],
            "clipped_area_km2": cell["clipped_area_km2"],
            "coverage_ratio": cell["coverage_ratio"],
            "centroid_x_m": centroid.x,
            "centroid_y_m": centroid.y,
            "neighbors_4": json.dumps(
                cell["neighbors_4"]
            ),
            "neighbors_8": json.dumps(
                cell["neighbors_8"]
            ),
            "geometry": cell["geometry"]
        })

    grid = gpd.GeoDataFrame(
        records,
        geometry="geometry",
        crs=GRID_CRS
    )

    # Convert coordinates to latitude/longitude
    grid = grid.to_crs(OUTPUT_CRS)

    geojson_path = (
        output_dir / f"{region_name}_grid_5km.geojson"
    )

    grid.to_file(
        geojson_path,
        driver="GeoJSON"
    )

    metadata = {
        "project": "Earth Detective",
        "region": region_name,
        "grid_version": "1.0",
        "grid_type": "fixed",
        "cell_size_m": cell_size,
        "grid_crs": GRID_CRS,
        "output_crs": OUTPUT_CRS,
        "grid_origin_m": [
            GRID_ORIGIN_X,
            GRID_ORIGIN_Y
        ],
        "cell_count": len(cells),
        "neighbor_types": [
            "4-directional edge neighbors",
            "8-directional including corners"
        ],
        "data_values_included": False,
        "note": (
            "Grid geometry only. No rainfall, elevation, "
            "or vulnerability values have been assigned."
        )
    }

    metadata_path = (
        output_dir / f"{region_name}_grid_metadata.json"
    )

    with open(
        metadata_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metadata,
            file,
            indent=2
        )

    print("\nGrid generation completed!")
    print("Region:", region_name)
    print("Cell size:", cell_size, "meters")
    print("Number of cells:", len(cells))
    print("GeoJSON:", geojson_path)
    print("Metadata:", metadata_path)


def main():

    parser = argparse.ArgumentParser(
        description="Earth Detective Universal Grid V1"
    )

    parser.add_argument(
        "--boundary",
        type=str,
        help="Path to a polygon GeoJSON boundary"
    )

    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="Rectangular study extent"
    )

    parser.add_argument(
        "--region",
        type=str,
        default="study_area"
    )

    parser.add_argument(
        "--cell-size",
        type=int,
        default=GRID_SIZE_M
    )

    parser.add_argument(
        "--output",
        type=str,
        default="data/processed/grids"
    )

    args = parser.parse_args()

    if bool(args.boundary) == bool(args.bbox):
        parser.error(
            "Provide exactly one of --boundary or --bbox."
        )

    region = load_region(
        boundary_path=args.boundary,
        bbox=args.bbox
    )

    cells = generate_grid(
        region,
        cell_size=args.cell_size
    )

    cells = add_neighbors(cells)

    export_grid(
        cells,
        args.output,
        args.region,
        args.cell_size
    )


if __name__ == "__main__":
    main()
