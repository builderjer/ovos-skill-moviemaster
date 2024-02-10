import json
from datetime import datetime

# Manually define the non-EOL Python versions and their EOL dates
# Update this as new releases come out or old versions reach EOL
python_versions = {
    "3.8": "2024-10-01",
    "3.9": "2025-10-01",
    "3.10": "2026-10-01",
    "3.11": "2027-10-01",
    #"3.12": "2028-10-01"
}

# Get the current date
current_date = datetime.now().date()

# Filter out versions that are past their EOL
non_eol_versions = {version: eol_date for version, eol_date in python_versions.items()
                    if datetime.strptime(eol_date, "%Y-%m-%d").date() > current_date}

# Prepare the data for the JSON file
data = {
    "schemaVersion": 1,
    "label": "python",
    "message": ", ".join(non_eol_versions.keys()),
    "color": "blue"
}

# Write the data to a JSON file
with open("supported_py_versions.json", "w") as file:
    json.dump(data, file)

print("Updated python-versions.json with non-EOL Python versions.")