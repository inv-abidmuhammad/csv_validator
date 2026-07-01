import argparse
import json
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from validator.logger_config import setup_logger
from dotenv import load_dotenv

load_dotenv()
setup_logger()
logger = logging.getLogger(__name__)

from validator.file_utils import generate_file_hash, generate_combined_hash
from validator.scanner import get_csv_files, get_schema_files
from validator.schema_loader import load_schema
from validator.csv_reader import read_csv
from validator.validation_engine import validate_csv
from validator.report_generator import generate_report
from validator.notifier import send_report_email, send_batch_report_email
from validator.progress import ProgressReporter
from validator.tracker import (
    initialize_db,
    FAILED,
    SUCCESS,
    get_file_status,
    get_report_path,
    record_result
)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="CSV Validation Application")
parser.add_argument("--file", help="Single CSV filename to validate (must be in input folder)")
parser.add_argument("--schema", help="Schema filename to use (must be in schema folder). "
                                     "Required in single mode. In batch mode, skips the interactive prompt.")
args = parser.parse_args()

single_mode = args.file is not None

if single_mode and not args.schema:
    parser.error("--file and --schema must be provided together for a single run.")

# ---------------------------------------------------------------------------
# Config & DB
# ---------------------------------------------------------------------------

logger.info("CSV Validation Application Started")

try:
    with open("config/config.json") as config_file:
        config = json.load(config_file)
except FileNotFoundError:
    logger.critical("Config file 'config/config.json' missing.")
    sys.exit(1)

db_path = config["database_path"]
initialize_db(db_path)


def resolve_smtp_config():
    """
    Returns a usable SMTP config dict if email is enabled, else None.
    Prefers an explicit password in config, but falls back to the
    SMTP_PASSWORD environment variable so credentials don't need to
    live in config.json in plaintext.
    """
    email_config = config.get("email")

    if not email_config or not email_config.get("enabled", False):
        return None

    smtp_config = dict(email_config)
    if not smtp_config.get("password"):
        smtp_config["password"] = os.getenv("SMTP_PASSWORD")

    return smtp_config


def maybe_send_report_email(report_path, tag=""):
    """
    Sends a single report via email. Used by single/independent mode,
    where there's exactly one report — no batching needed.

    Never raises — a broken mail server should not crash a validation run,
    especially under cron where nobody is watching to retry by hand.
    """
    smtp_config = resolve_smtp_config()

    if not smtp_config:
        return

    try:
        send_report_email(report_path, smtp_config)
        logger.info(f"{tag}Report emailed to {smtp_config.get('to_address')}")
    except Exception as e:
        logger.error(f"{tag}Failed to send report email: {e}")


def maybe_send_batch_report_email(report_paths, summary):
    """
    Sends one email for an entire batch run, with all reports zipped into
    a single attachment. Used by batch mode so that processing 50 files
    results in 1 email, not 50.

    Never raises — see maybe_send_report_email for rationale.
    """
    smtp_config = resolve_smtp_config()

    if not smtp_config or not report_paths:
        return

    try:
        send_batch_report_email(report_paths, smtp_config, summary)
        logger.info(
            f"Batch report emailed to {smtp_config.get('to_address')} "
            f"({len(report_paths)} report(s) attached)"
        )
    except Exception as e:
        logger.error(f"Failed to send batch report email: {e}")

# ---------------------------------------------------------------------------
# Single mode
# ---------------------------------------------------------------------------

if single_mode:
    logger.info(f"[INDEPENDENT RUN] File: {args.file} | Schema: {args.schema}")

    csv_path = Path(config["input_folder"]) / args.file
    schema_path = Path(config["schema_folder"]) / args.schema

    if not csv_path.exists():
        logger.critical(f"[INDEPENDENT RUN] File not found in input folder: {args.file}")
        sys.exit(1)

    if not schema_path.exists():
        logger.critical(f"[INDEPENDENT RUN] Schema not found in schema folder: {args.schema}")
        sys.exit(1)

    try:
        schema = load_schema(schema_path)
        logger.info(f"[INDEPENDENT RUN] Schema loaded successfully: {args.schema}")
    except ValueError as e:
        logger.error(f"[INDEPENDENT RUN] Schema validation failed: {e}")
        sys.exit(1)

    try:
        df = read_csv(csv_path)
    except Exception as e:
        logger.error(f"[INDEPENDENT RUN] Failed to read/parse {args.file}: {e}")
        sys.exit(1)

    logger.info(f"[INDEPENDENT RUN] Processing file: {args.file}")

    errors = validate_csv(df, schema)

    logger.info(
        f"[INDEPENDENT RUN] Validation completed for {args.file}. "
        f"Found {len(errors)} errors."
    )

    report_formats = set(config.get("report_formats", []))
    smtp_config_check = resolve_smtp_config()
    if smtp_config_check:
        report_formats.add("csv")

    report_path = generate_report(
        args.file, args.schema, df, errors, config["report_folder"],
        formats=list(report_formats)
    )
    logger.info(f"[INDEPENDENT RUN] Report generated: {report_path}")

    if smtp_config_check:
        csv_report_path = report_path.with_suffix(".csv")
        maybe_send_report_email(csv_report_path, tag="[INDEPENDENT RUN] ")

    result = FAILED if errors else SUCCESS

    combined_hash = generate_combined_hash(
        generate_file_hash(csv_path),
        generate_file_hash(schema_path)
    )
    record_result(db_path, combined_hash, args.file, result, report_path)

    logger.info(f"[INDEPENDENT RUN] Result: {result} | Report: {report_path}")
    logger.info("[INDEPENDENT RUN] Finished")
    sys.exit(0)

# ---------------------------------------------------------------------------
# Batch mode
# ---------------------------------------------------------------------------

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

if args.schema:
    # Schema provided via flag — skip interactive prompt
    schema_path = Path(config["schema_folder"]) / args.schema
    if not schema_path.exists():
        logger.critical(f"Schema not found in schema folder: {args.schema}")
        sys.exit(1)
    selected_schema = schema_path
    logger.info(f"Schema selected via argument: {args.schema}")
elif len(schema_files) > 1:
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

batch_smtp_config = resolve_smtp_config()
batch_report_formats = set(config.get("report_formats", []))
if batch_smtp_config:
    batch_report_formats.add("csv")

batch_report_paths = []
batch_summary = {
    "schema": selected_schema.name,
    "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
    "processed": 0,
    "passed": 0,
    "failed": 0,
    "skipped": 0,
}

progress = ProgressReporter(total=len(csv_files), label="Validating files")

for csv_file in csv_files:
    progress.update(csv_file.name)

    file_hash = generate_file_hash(csv_file)
    combined_hash = generate_combined_hash(file_hash, schema_hash)

    status = get_file_status(db_path, combined_hash)

    if status:
        logger.info(
            f"File {csv_file.name} skipped. Already processed with this schema "
            f"with status: {status}.\n"
            f"Existing Report: {get_report_path(db_path, combined_hash)}"
        )
        batch_summary["skipped"] += 1
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
        selected_schema.name,
        df,
        errors,
        config["report_folder"],
        formats=list(batch_report_formats)
    )

    logger.info(f"Report generated: {report_path}")

    batch_summary["processed"] += 1
    if errors:
        batch_summary["failed"] += 1
    else:
        batch_summary["passed"] += 1

    if batch_smtp_config:
        batch_report_paths.append(report_path.with_suffix(".csv"))

    result = FAILED if errors else SUCCESS

    record_result(
        db_path,
        combined_hash,
        csv_file.name,
        result,
        report_path
    )

    logger.info(f"Stored execution result for {csv_file.name}: {result}\n")

maybe_send_batch_report_email(batch_report_paths, batch_summary)

progress.finish()

logger.info("All files processed. CSV Validation Application Finished")