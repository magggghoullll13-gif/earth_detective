
import earthaccess
from datetime import datetime, timedelta, timezone
from collections import Counter

# ==========================================
# EARTH DETECTIVE - IMERG METADATA CHECK
# ==========================================

print("Connecting to NASA Earthdata...")
earthaccess.login(strategy="interactive", persist=True)

print("Searching IMERG Final V07...")

granules = earthaccess.search_data(
    short_name="GPM_3IMERGHH",
    version="07",
    daac="GES_DISC",
    cloud_hosted=True,
    temporal=(
        "2022-08-01T00:00:00",
        "2022-08-31T23:59:59"
    ),
    bounding_box=(66, 23.5, 71.5, 28.5),
    count=-1
)

# ==========================================
# VALIDATE TIMESTAMPS
# ==========================================

def get_beginning(granule):
    temporal = granule.get("umm", {}).get("TemporalExtent", {})
    return temporal.get("RangeDateTime", {}).get("BeginningDateTime")


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


granule_times = []

for granule in granules:
    value = get_beginning(granule)

    if value:
        granule_times.append(parse_time(value))

expected_start = datetime(2022, 8, 1, tzinfo=timezone.utc)

expected_times = {
    expected_start + timedelta(minutes=30 * i)
    for i in range(1488)
}

counts = Counter(granule_times)
actual_times = set(granule_times)

missing = sorted(expected_times - actual_times)
duplicates = [t for t, count in counts.items() if count > 1]

print("\n========== TEMPORAL VALIDATION ==========")
print("Granules:", len(granules))
print("Valid timestamps:", len(granule_times))
print("Unique timestamps:", len(actual_times))
print("Missing timestamps:", len(missing))
print("Duplicate timestamps:", len(duplicates))

if granule_times:
    print("First observation:", min(granule_times))
    print("Last observation:", max(granule_times))

# ==========================================
# INSPECT FIRST GRANULE
# ==========================================

first = min(
    granules,
    key=lambda g: get_beginning(g) or "9999"
)

umm = first.get("umm", {})

print("\n========== SAMPLE GRANULE ==========")
print("Granule ID:", umm.get("GranuleUR"))
print("Start:", get_beginning(first))

related_urls = umm.get("RelatedUrls", [])

opendap_links = [
    link["URL"]
    for link in related_urls
    if link.get("Type") == "USE SERVICE API"
    and link.get("Subtype") == "OPENDAP DATA"
]

download_links = [
    link["URL"]
    for link in related_urls
    if link.get("Type") == "GET DATA"
]

print("\nOPeNDAP links found:", len(opendap_links))
print("Direct download links found:", len(download_links))

for link in opendap_links[:2]:
    print("OPeNDAP:", link)

for link in download_links[:2]:
    print("Download:", link)

# ==========================================
# FINAL RESULT
# ==========================================

print("\n========== FINAL RESULT ==========")

if len(granules) == 1488 and not missing and not duplicates:
    print("SUCCESS: All 1,488 timestamps are present.")
else:
    print("WARNING: Investigate temporal coverage.")

print("No files downloaded.")
