from pathlib import Path


def get_csv_files(input_folder):
    return list(Path(input_folder).glob("*.csv"))


def get_schema_files(schema_folder):
    return list(Path(schema_folder).glob("*.json"))