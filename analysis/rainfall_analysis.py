
from pathlib import Path
import json
import pandas as pd

# ==========================================
# 1. FILE PATHS
# ==========================================

ROOT = Path(__file__).resolve().parent.parent

INPUT = ROOT / "data/raw/pakistan/imerg_august_2022.csv"
OUTPUT = ROOT / "data/processed/pakistan_rainfall_2022.json"

# ==========================================
# 2. READ NASA DATA
# ==========================================

# NASA Giovanni CSV contains 8 metadata lines
# before the actual column headers.

df = pd.read_csv(INPUT, skiprows=8)

# Remove spaces from column names
df.columns = df.columns.str.strip()

print("Columns:", df.columns.tolist())

# Actual NASA columns
date_col = "time"
rain_col = "mean_GPM_3IMERGDF_07_precipitation"

# ==========================================
# 3. CLEAN DATA
# ==========================================

# Convert dates
df["date"] = pd.to_datetime(
    df[date_col],
    format="%Y-%m-%d",
    errors="raise"
)

# Convert rainfall values to numbers
df["rainfall_mm"] = pd.to_numeric(
    df[rain_col],
    errors="coerce"
)

# NASA missing-data value is -9999.9
df.loc[
    df["rainfall_mm"] <= -9999,
    "rainfall_mm"
] = float("nan")

# Remove invalid observations
df = df.dropna(
    subset=["date", "rainfall_mm"]
)

# Sort by date
df = df.sort_values("date")

# ==========================================
# 4. VALIDATE DATA
# ==========================================

assert len(df) == 31, (
    "Expected 31 valid daily observations"
)

assert df["date"].is_unique, (
    "Duplicate dates found"
)

assert (df["rainfall_mm"] >= 0).all(), (
    "Invalid negative rainfall values"
)

expected_dates = pd.date_range(
    "2022-08-01",
    "2022-08-31",
    freq="D"
)

assert df["date"].reset_index(drop=True).equals(
    pd.Series(expected_dates)
), "Missing or unexpected observation dates"

print("NASA data validation passed!")

# ==========================================
# 5. CALCULATE RAINFALL STATISTICS
# ==========================================

rain = df["rainfall_mm"]

# Total monthly rainfall
total_rainfall = round(
    float(rain.sum()), 2
)

# Rainy days: rainfall >= 1 mm
rainy_days = int(
    (rain >= 1).sum()
)

# Heavy rainfall days: rainfall >= 10 mm
heavy_rain_days = int(
    (rain >= 10).sum()
)

# Maximum daily rainfall
max_daily_rainfall = round(
    float(rain.max()), 2
)

# Date of maximum rainfall
max_rain_date = df.loc[
    rain.idxmax(), "date"
].strftime("%Y-%m-%d")

# Average daily rainfall
average_daily_rainfall = round(
    float(rain.mean()), 2
)

# Consecutive rainy days
max_consecutive_rainy_days = 0
current_streak = 0

for value in rain:
    if value >= 1:
        current_streak += 1

        max_consecutive_rainy_days = max(
            max_consecutive_rainy_days,
            current_streak
        )
    else:
        current_streak = 0

# ==========================================
# 6. PREPARE DAILY CHART DATA
# ==========================================

daily_rainfall = []

for _, row in df.iterrows():
    daily_rainfall.append({
        "date": row["date"].strftime("%Y-%m-%d"),
        "rainfallMm": round(
            float(row["rainfall_mm"]), 3
        )
    })

# ==========================================
# 7. PREPARE JSON FOR NEXT.JS
# ==========================================

result = {
    "regionId": "pakistan-sindh-study-area",
    "regionName": "Pakistan — Sindh study area",

    "period": {
        "start": "2022-08-01",
        "end": "2022-08-31"
    },

    "rainfall": {
        "totalMm": total_rainfall,
        "rainyDays": rainy_days,
        "rainyDayThresholdMm": 1,
        "heavyRainDays": heavy_rain_days,
        "heavyRainThresholdMm": 10,
        "maxDailyMm": max_daily_rainfall,
        "maxDailyDate": max_rain_date,
        "averageDailyMm": average_daily_rainfall,
        "maxConsecutiveRainyDays": max_consecutive_rainy_days
    },

    "dailyRainfall": daily_rainfall,

    "source": {
        "provider": "NASA",
        "mission": "GPM",
        "dataset": "IMERG Final Run V07",
        "product": "GPM_3IMERGDF",
        "variable": "precipitation",
        "aggregation": "Area-averaged daily precipitation",
        "units": "mm/day",
        "boundingBox": [
            66,
            23.5,
            71.5,
            28.5
        ]
    },

    "limitations": [
        "Results represent regional mean rainfall.",
        "These are not individual grid-cell measurements.",
        "Rainy days use a regional mean threshold of 1 mm/day.",
        "Flood vulnerability is not calculated by this script."
    ]
}

# ==========================================
# 8. SAVE JSON FILE
# ==========================================

OUTPUT.parent.mkdir(
    parents=True,
    exist_ok=True
)

with open(
    OUTPUT,
    "w",
    encoding="utf-8"
) as file:
    json.dump(
        result,
        file,
        indent=2,
        ensure_ascii=False
    )

# ==========================================
# 9. PRINT RESULTS
# ==========================================

print("\n================================")
print("EARTH DETECTIVE — NASA ANALYSIS")
print("================================")

print("Region: Sindh study area, Pakistan")
print("Period: August 2022")

print(f"Total rainfall: {total_rainfall} mm")
print(f"Rainy days: {rainy_days}")
print(f"Heavy rainfall days: {heavy_rain_days}")
print(f"Maximum daily rainfall: {max_daily_rainfall} mm")
print(f"Maximum rainfall date: {max_rain_date}")
print(f"Average daily rainfall: {average_daily_rainfall} mm")
print(
    "Maximum consecutive rainy days:",
    max_consecutive_rainy_days
)

print("\nNASA data processed successfully!")
print(f"JSON saved to: {OUTPUT}")
