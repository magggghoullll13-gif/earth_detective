
from pathlib import Path
from datetime import datetime, timedelta, timezone

import earthaccess

from harmony import BBox, Client, Collection, Request


# ==========================================
# CONFIGURATION
# ==========================================

COLLECTION_ID = "C2723754847-GES_DISC"

START = datetime(
    2022, 8, 1, 0, 0,
    tzinfo=timezone.utc
)

STOP = datetime(
    2022, 8, 1, 11, 59, 59,
    tzinfo=timezone.utc
)

EXPECTED_COUNT = 24

BBOX = (66.0, 23.5, 71.5, 28.5)

OUTPUT_DIR = Path(
    "data/raw/pakistan/imerg_half_hourly/"
    "2022-08-01_00-12"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# 1. AUTHENTICATION
# ==========================================

print("Authenticating NASA Earthdata...")

earthaccess.login(
    strategy="interactive",
    persist=True
)


# ==========================================
# 2. SEARCH THE FIRST 12 HOURS
# ==========================================

print("\nSearching first 12 hours...")

granules = earthaccess.search_data(
    short_name="GPM_3IMERGHH",
    version="07",
    daac="GES_DISC",
    cloud_hosted=True,
    temporal=(
        "2022-08-01T00:00:00",
        "2022-08-01T11:59:59"
    ),
    bounding_box=BBOX,
    count=-1
)


def get_start(granule):
    return granule["umm"]["TemporalExtent"][
        "RangeDateTime"
    ]["BeginningDateTime"]


granules = sorted(
    granules,
    key=get_start
)

granule_names = [
    g["umm"]["GranuleUR"]
    for g in granules
]

print("Granules found:", len(granule_names))


# ==========================================
# 3. VERIFY EXACT TEMPORAL COVERAGE
# ==========================================

actual_times = [
    datetime.fromisoformat(
        get_start(g).replace("Z", "+00:00")
    )
    for g in granules
]

expected_times = [
    START + timedelta(minutes=30 * i)
    for i in range(EXPECTED_COUNT)
]

if len(granules) != EXPECTED_COUNT:
    raise RuntimeError(
        f"Expected 24 granules, found {len(granules)}"
    )

if actual_times != expected_times:
    raise RuntimeError(
        "Timestamp validation failed."
    )

print("All 24 timestamps verified.")


# ==========================================
# 4. CREATE HARMONY REQUEST
# ==========================================

request = Request(
    collection=Collection(id=COLLECTION_ID),

    granule_name=granule_names,

    spatial=BBox(*BBOX),

    variables=[
        "Grid/precipitation"
    ],

    format="application/netcdf",

    max_results=EXPECTED_COUNT
)

if not request.is_valid():
    raise RuntimeError(
        str(request.error_messages())
    )


# ==========================================
# 5. SUBMIT ONE HARMONY JOB
# ==========================================

client = Client()

print("\nSubmitting 24-granule request...")

job_id = client.submit(request)

print("Job ID:", job_id)

client.wait_for_processing(
    job_id,
    show_progress=True
)


# ==========================================
# 6. DOWNLOAD ALL 24 OUTPUTS
# ==========================================

print("\nDownloading spatial subsets...")

futures = client.download_all(
    job_id,
    directory=str(OUTPUT_DIR),
    overwrite=False
)

downloaded = [
    future.result()
    for future in futures
]

print("\n========== DOWNLOAD SUMMARY ==========")

print("Expected outputs:", EXPECTED_COUNT)
print("Downloaded outputs:", len(downloaded))

for path in downloaded:
    print(path)

if len(downloaded) != EXPECTED_COUNT:
    raise RuntimeError(
        "Output count does not match expected granules."
    )

print("\nSUCCESS: First 12-hour block acquired.")
