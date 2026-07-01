# CSV Validator

A command-line CSV validation tool. It reads CSV files against JSON-defined schemas, logs the run, generates reports (JSON/CSV/HTML), emails the reports, and keeps a local record of what's already been processed so re-runs don't redo work. Can be run manually, on a schedule (cron), or triggered automatically by watching a folder for new files.

## Features

- **Schema-driven validation** — column presence, required fields, data types (`string`, `int`, `float`, `boolean`), regex patterns, min/max ranges, uniqueness, duplicate row detection, and cross-field comparisons (e.g. `end_date` must be `greater_than` `start_date`).
- **Two run modes** — a single independent file+schema run, or a batch run over everything in the inputs folder.
- **Interactive or scripted schema selection** — prompts you to pick a schema when there's more than one and none was specified, or skips the prompt entirely when `--schema` is passed.
- **Skip already-processed files** — every (file + schema) combination is hashed and recorded in SQLite, so batch runs won't re-validate a file/schema pair that's already been processed successfully or unsuccessfully.
- **Multi-format reports** — JSON, CSV, and/or HTML reports per file, with a summary (rows processed/passed/failed, duplicate count, error breakdown by type) plus the row-by-row error list.
- **Email delivery** — single runs email the one CSV report; batch runs zip all CSV reports into one attachment and send a single summary email. Email is entirely optional and never crashes a run if it fails.
- **File watcher** — `watch.py` monitors the inputs folder and validates new files automatically as they land, with debouncing so partially-written/copied files aren't picked up mid-write.
- **Cron-friendly** — designed to run unattended once a day (or on any schedule); failures are logged, not raised, so a bad file or SMTP outage doesn't take down the whole run.
- **Logging** — every run writes to `logs/validator.log`.

## Project Structure

```
csv_validator/
├── main.py                  # entry point: single mode & batch mode
├── watch.py                 # entry point: folder watcher
├── config/
│   └── config.json          # paths, report formats, email settings
├── validator/                # core library code
├── inputs/                   # place CSV files to validate here
├── schemas/                  # place JSON schema files here
├── reports/                  # generated reports land here
├── logs/
│   └── validator.log         # all run logs
├── database/
│   └── validation.db         # SQLite, auto-created on first run
├── .env                       # SMTP_PASSWORD (not committed)
├── requirements.txt
└── tests/
```

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <your-repo-url>
cd csv_validator
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create the folder structure

The app expects these folders to exist relative to where you run it (create any that are missing):

```bash
mkdir -p inputs schemas reports logs database
```

`database/validation.db` doesn't need to be created manually — it's generated automatically the first time `main.py` runs.

### 4. Configure `config/config.json`

```json
{
    "input_folder": "inputs",
    "schema_folder": "schemas",
    "report_folder": "reports",
    "database_path": "database/validation.db",
    "report_formats": ["csv", "html"],
    "email": {
        "enabled": true,
        "host": "smtp.gmail.com",
        "port": 587,
        "username": "you@example.com",
        "from_address": "you@example.com",
        "to_address": "you@example.com",
        "use_tls": true
    }
}
```

- `report_formats` controls which formats get generated for every run (`json`, `csv`, `html` are supported). A CSV report is always generated in addition to whatever's listed here if email sending is enabled, since email attachments are CSV-only.
- Set `"email": {"enabled": false}` to turn off emailing entirely — validation and reports still run as normal, nothing gets sent.
- Don't put your real SMTP password in this file — leave `"password"` out of the email block entirely and set it in `.env` instead (see below).

### 5. Configure `.env`

Create a `.env` file in the project root (this file should **not** be committed to version control):

```dotenv
SMTP_PASSWORD=your app password here
```

For Gmail, this needs to be a [Google App Password](https://myaccount.google.com/apppasswords), not your normal account password (this requires 2-Step Verification to be enabled on the account).

### 6. Add schema files

Drop one or more JSON schema files into `schemas/`. Format:

```json
{
    "columns": {
        "id": { "type": "int", "required": true, "unique": true },
        "email": { "type": "string", "required": true, "pattern": "^[^@]+@[^@]+\\.[^@]+$" },
        "age": { "type": "int", "required": false, "min": 0, "max": 120 },
        "signup_date": { "type": "string", "required": true },
        "expiry_date": { "type": "string", "required": true }
    },
    "cross_field_rules": [
        { "type": "greater_than", "field": "expiry_date", "than": "signup_date" }
    ]
}
```

Supported column keys: `type` (`string`/`int`/`float`/`boolean`, required), `required` (bool, required), `pattern` (regex string, optional), `min`/`max` (numeric, optional), `unique` (bool, optional).

Supported `cross_field_rules` types: `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal`, `not_equal`.

## Usage

Activate the venv first: `source venv/bin/activate`.

### Single / independent run

Validates one specific file against one specific schema, regardless of what else is sitting in the inputs folder. Always sends its report by email as a single CSV (if email is enabled) rather than a zip.

```bash
python main.py --file customers.csv --schema customer_schema.json
```

Both `--file` and `--schema` are required together in this mode. `--file` must exist in `inputs/`, `--schema` must exist in `schemas/`.

### Batch run — schema specified

Validates every CSV file in `inputs/` against the given schema, skipping the interactive prompt. All reports are zipped into a single attachment and sent in one summary email.

```bash
python main.py --schema customer_schema.json
```

### Batch run — no schema specified

```bash
python main.py
```

- If there's exactly one schema file in `schemas/`, it's used automatically.
- If there are multiple, you'll be prompted to pick one from a numbered list.

### Watch mode

Runs continuously and validates any new (or modified) CSV file that shows up in `inputs/`, using the given schema. Each detected file is debounced for a couple of seconds after it stops changing (to avoid validating a half-copied file) and then run through `main.py` in single mode.

```bash
python watch.py --schema customer_schema.json
```

Optional: `--quiet-seconds N` to change the debounce window (default 2.0 seconds).

Stop with `Ctrl+C`.

### Re-running files

Batch mode records every (file + schema) combination it processes in `database/validation.db`. If you run batch mode again without changing the file or the schema, that file is skipped (logged as already processed) rather than re-validated. Single mode also records results but doesn't consult them to skip a run — it always runs the file you explicitly asked for.

To force re-validation of a file, either change the file's contents (the hash changes) or remove its row from the database.

## Scheduling with cron

To run a daily batch validation automatically (e.g. at 2:00 AM):

```bash
crontab -e
```

Add a line like:

```cron
0 2 * * * cd /path/to/csv_validator && /path/to/csv_validator/venv/bin/python main.py --schema customer_schema.json >> logs/cron.log 2>&1
```

- Always use the full path to the venv's Python interpreter and `cd` into the project directory first, since cron doesn't activate your shell environment or use relative paths.
- Use `--schema` explicitly in the cron job to avoid an interactive prompt, which cron has no way to answer.
- View the current crontab with `crontab -l`.
- Even if `logs/validator.log` already captures the run, redirecting stdout/stderr to a separate file (as above) is useful for catching anything printed outside the logger (e.g. an uncaught exception before logging is set up).

## Logs

Every run — single, batch, or watcher-triggered — appends to `logs/validator.log`, including schema load errors, file read errors, per-file validation results, skipped files, and email send failures. Nothing about a failure crashes the whole run except missing config or missing schema files in batch mode.

## Reports

For each validated file, a report is generated in `reports/` in whichever formats are configured (`json`, `csv`, `html`), containing:
- A summary: rows processed, rows passed, rows failed, duplicate count, and a breakdown of error counts by type.
- The full row-by-row error list (row number, column, value, and error message).

## Running tests

```bash
pip install -r requirements.txt   # pytest is included
pytest
```

## Troubleshooting

- **"Config file 'config/config.json' missing"** — run commands from the project root, or check the path.
- **"No schema files found in schema directory"** — add at least one `.json` schema file to `schemas/`.
- **Email not sending** — check `logs/validator.log` for the specific SMTP error; failures are logged, not raised. Common causes: wrong app password in `.env`, `enabled: false` in config, or the mail provider blocking less-secure app access.
- **File skipped unexpectedly in batch mode** — it's likely already been processed with that exact schema; check `database/validation.db` or just look for the "already processed" log line, which also gives you the existing report path.