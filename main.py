import json
import sys
import logging
from validator.logger_config import setup_logger

setup_logger()
logger = logging.getLogger(__name__)

from validator.file_utils import generate_file_hash, generate_combined_hash
from validator.scanner import get_csv_files, get_schema_files
from validator.schema_loader import load_schema
from validator.csv_reader import read_csv
from validator.validation_engine import validate_csv
from validator.report_generator import generate_report
from validator.tracker import (
    initialize_db,
    FAILED,
    SUCCESS,
    get_file_status,
    get_report_path,
    record_result
)

logger.info("CSV Validation Application Started")

try:
    with open("config/config.json") as config_file:
        config = json.load(config_file)
except FileNotFoundError:
    logger.critical("Config file 'config/config.json' missing.")
    sys.exit(1)

db_path = config["database_path"]
initialize_db(db_path)

csv_files = get_csv_files(config["input_folder"])
schema_files = get_schema_files(config["schema_folder"])

print("CSV Files:")
if not csv_files:
    logger.warning("No CSV files found in input directory. Exiting.")
    sys.exit(0)
for index, file in enumerate(csv_files, start=1):
    print(f"{index}. {file.name}")

print()

print("Schema Files:")
if not schema_files:
    logger.critical("No schema files found in schema directory. Exiting.")
    sys.exit(1)
for index, file in enumerate(schema_files, start=1):
    print(f"{index}. {file.name}")

print()

if len(schema_files) > 1:
    print("Multiple schema files found. Please select the one to use for validation:")
    while True:
        try:
            choice = int(input("Select schema number: "))
            if 1 <= choice <= len(schema_files):
                selected_schema = schema_files[choice - 1]
                break
            print(f"Please enter a number between 1 and {len(schema_files)}.")
        except ValueError:
            print("Invalid input. Please enter a valid integer.")
else:
    selected_schema = schema_files[0]

logger.info(f"Selected schema: {selected_schema.name}")

try:
    schema = load_schema(selected_schema)
    logger.info(f"Schema loaded successfully: {selected_schema.name}")
    print(schema)
except ValueError as e:
    logger.error(f"Schema validation layout failed: {e}")
    sys.exit(1)

schema_hash = generate_file_hash(selected_schema)

for csv_file in csv_files:
    file_hash = generate_file_hash(csv_file)
    combined_hash = generate_combined_hash(file_hash, schema_hash)

    status = get_file_status(db_path, combined_hash)

    if status:
        logger.info(
            f"File {csv_file.name} skipped. Already processed with this schema "
            f"with status: {status}.\n"
            f"Existing Report: {get_report_path(db_path, combined_hash)}"
        )
        continue

    try:
        df = read_csv(csv_file)
    except Exception as e:
        logger.error(f"Failed to read/parse {csv_file.name}: {e}")
        continue

    logger.info(f"Processing file: {csv_file.name}")

    errors = validate_csv(df, schema)

    logger.info(
        f"Validation completed for {csv_file.name}. "
        f"Found {len(errors)} errors."
    )

    report_path = generate_report(
        csv_file.name,
        errors,
        config["report_folder"]
    )

    logger.info(f"Report generated: {report_path}")

    result = FAILED if errors else SUCCESS

    record_result(
        db_path,
        combined_hash,
        csv_file.name,
        result,
        report_path
    )

    logger.info(f"Stored execution result for {csv_file.name}: {result}\n")

logger.info("All files processed. CSV Validation Application Finished")