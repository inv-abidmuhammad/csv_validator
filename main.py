import json
import sys

from validator.scanner import get_csv_files, get_schema_files
from validator.schema_loader import load_schema
from validator.csv_reader import read_csv
from validator.validation_engine import validate_columns, validate_required_fields, validate_duplicates

with open("config/config.json") as config_file:
    config = json.load(config_file)

csv_files = get_csv_files(config["input_folder"])
schema_files = get_schema_files(config["schema_folder"])

print("CSV Files:")
if not csv_files:
    print("No CSV files found.")
    sys.exit(1)
for index, file in enumerate(csv_files, start=1):
    print(f"{index}. {file.name}")

print()

print("Schema Files:")
if not schema_files:
    print("No schema files found.")
    sys.exit(1)
for index, file in enumerate(schema_files, start=1):
    print(f"{index}. {file.name}")

print()

if len(schema_files) > 1:
    print("Multiple schema files found. Please select the one to use for validation:")
    try:
        choice = int(input("Select schema: "))
        if choice < 1 or choice > len(schema_files):
            raise ValueError
    except ValueError:
        print("Please enter a valid number.")
        sys.exit(1)
    selected_schema = schema_files[choice - 1]
else:
    selected_schema = schema_files[0]

print(f"Using schema: {selected_schema.name}")

try:
    schema = load_schema(selected_schema)
    print(f"Loaded schema: ")
    print(schema)
except ValueError as e:
    print(f"Error loading schema: {e}")
    sys.exit(1)

try:
    df = read_csv(csv_files[0])
    print(df.head())
except Exception as e:
    print(f"Error reading CSV file: {e}")
    sys.exit(1)

column_errors = validate_columns(df, schema)
required_field_errors = validate_required_fields(df, schema)
duplicate_errors = validate_duplicates(df)

all_errors = (
    column_errors +
    required_field_errors +
    duplicate_errors
)

print(all_errors)

