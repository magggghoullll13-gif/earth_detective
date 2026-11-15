
from pathlib import Path

from harmony import BBox, Client, Collection, Request
from netCDF4 import Dataset

# ==========================================
# EARTH DETECTIVE
# FIRST SPATIAL IMERG EXTRACTION
# ==========================================

COLLECTION_ID = "C2723754847-GES_DISC"

GRANULE_NAME = (
    "GPM_3IMERGHH.07:"
    "3B-HHR.MS.MRG.3IMERG."
    "20220801-S000000-E002959.0000.V07B.HDF5"
)

OUTPUT_DIR = Path(
    "data/raw/pakistan/imerg_half_hourly/test"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Starting NASA Harmony client...")

client = Client()

# ==========================================
# CREATE EXTRACTION REQUEST
# ==========================================

request = Request(
    collection=Collection(id=COLLECTION_ID),

    granule_name=[GRANULE_NAME],

    spatial=BBox(
        66.0,
        23.5,
        71.5,
        28.5
    ),

    variables=[
        "Grid/precipitation"
    ],

    format="application/netcdf",

    max_results=1
)

if not request.is_valid():
    raise RuntimeError(
        f"Invalid Harmony request: {request.error_messages()}"
    )

print("\nRequest validated successfully.")

# ==========================================
# SUBMIT TO NASA HARMONY
# ==========================================

print("\nSubmitting spatial extraction...")

job_id = client.submit(request)

print("Harmony Job ID:", job_id)

# ==========================================
# WAIT FOR PROCESSING
# ==========================================

print("\nWaiting for NASA processing...")

client.wait_for_processing(
    job_id,
    show_progress=True
)

print("\nNASA processing completed.")

# ==========================================
# DOWNLOAD RESULT
# ==========================================

print("\nDownloading subsetted NetCDF...")

futures = client.download_all(
    job_id,
    directory=str(OUTPUT_DIR),
    overwrite=False
)

downloaded_files = [
    future.result()
    for future in futures
]

if not downloaded_files:
    raise RuntimeError("No output files were returned.")

print("\nDownloaded files:")

for file_path in downloaded_files:
    print(file_path)

# ==========================================
# INSPECT NETCDF STRUCTURE
# ==========================================

def inspect_group(group, name="/"):

    print(f"\nGROUP: {name}")

    print("Dimensions:")

    for dim_name, dim in group.dimensions.items():
        print(f"  {dim_name}: {len(dim)}")

    print("Variables:")

    for var_name, var in group.variables.items():

        print(f"\n  Variable: {var_name}")
        print(f"  Shape: {var.shape}")
        print(f"  Dimensions: {var.dimensions}")
        print(f"  Units: {getattr(var, 'units', 'Not specified')}")
        print(
            f"  Long name: "
            f"{getattr(var, 'long_name', 'Not specified')}"
        )

    for child_name, child in group.groups.items():
        inspect_group(child, f"{name}{child_name}/")


print("\n========== NETCDF INSPECTION ==========")

for file_path in downloaded_files:

    with Dataset(file_path, "r") as dataset:

        print("\nFile:", file_path)

        print("\nGlobal attributes:")

        for attr in dataset.ncattrs():
            print(f"  {attr}: {dataset.getncattr(attr)}")

        inspect_group(dataset)

print("\n========================================")
print("FIRST SPATIAL EXTRACTION COMPLETED!")
