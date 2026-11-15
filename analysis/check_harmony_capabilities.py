
import json
from pathlib import Path

import earthaccess

# ==========================================
# EARTH DETECTIVE - HARMONY CAPABILITIES
# ==========================================

COLLECTION_ID = "C2723754847-GES_DISC"

print("Authenticating with NASA Earthdata...")

earthaccess.login(strategy="all")

session = earthaccess.get_requests_https_session()

# ==========================================
# REQUEST COLLECTION CAPABILITIES
# ==========================================

url = "https://harmony.earthdata.nasa.gov/capabilities"

params = {
    "collectionId": COLLECTION_ID,
    "version": 3
}

print("\nChecking NASA Harmony...")

response = session.get(
    url,
    params=params,
    timeout=60
)

print("HTTP status:", response.status_code)

response.raise_for_status()

capabilities = response.json()

# ==========================================
# DISPLAY COLLECTION INFORMATION
# ==========================================

print("\n========== COLLECTION ==========")

print("Concept ID:", capabilities.get("conceptId"))
print("Short name:", capabilities.get("shortName"))

print("\n========== SUMMARY ==========")

print(json.dumps(
    capabilities.get("summary", {}),
    indent=2
))

# ==========================================
# DISPLAY AVAILABLE SERVICES
# ==========================================

print("\n========== SERVICES ==========")

for service in capabilities.get("services", []):
    print(json.dumps(service, indent=2))

# ==========================================
# CHECK PRECIPITATION VARIABLE
# ==========================================

print("\n========== PRECIPITATION VARIABLES ==========")

for variable in capabilities.get("variables", []):
    if "precipitation" in json.dumps(variable).lower():
        print(json.dumps(variable, indent=2))

# ==========================================
# SAVE CAPABILITIES
# ==========================================

output = Path(
    "data/processed/metadata/"
    "imerg_harmony_capabilities_v07.json"
)

output.parent.mkdir(
    parents=True,
    exist_ok=True
)

output.write_text(
    json.dumps(capabilities, indent=2),
    encoding="utf-8"
)

print("\n========== COMPLETE ==========")
print("Capabilities saved to:", output)
print("No rainfall data downloaded.")
