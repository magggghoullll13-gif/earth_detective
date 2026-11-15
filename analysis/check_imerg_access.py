
import earthaccess

# ==========================================
# EARTH DETECTIVE - IMERG ACCESS CHECK
# ==========================================

print("Connecting to NASA Earthdata...")

auth = earthaccess.login(
    strategy="interactive",
    persist=True
)

if not auth.authenticated:
    raise RuntimeError("NASA Earthdata authentication failed.")

print("Authentication successful!")

# ==========================================
# SEARCH NASA IMERG FINAL V07
# ==========================================

print("\nSearching NASA IMERG granules...")

granules = earthaccess.search_data(
    short_name="GPM_3IMERGHH",
    version="07",
    daac="GES_DISC",
    cloud_hosted=True,
    temporal=(
        "2022-08-01T00:00:00",
        "2022-08-31T23:59:59"
    ),
    bounding_box=(
        66.0,
        23.5,
        71.5,
        28.5
    ),
    count=-1
)

# ==========================================
# DISPLAY RESULTS
# ==========================================

expected = 31 * 48

print("\n========== SEARCH RESULTS ==========")

print("Dataset: GPM_3IMERGHH")
print("Version: V07")
print("Run: Final")
print("Region: Sindh, Pakistan")
print("Period: August 2022")

print(f"\nGranules found: {len(granules)}")
print(f"Expected granules: {expected}")

if len(granules) == expected:
    print("\nSUCCESS: All 1,488 granules found!")
else:
    print("\nWARNING: Unexpected granule count.")
    print("We must investigate before downloading.")

print("\nNo data files have been downloaded yet.")
print("====================================")
