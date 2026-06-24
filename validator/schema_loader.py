import json

SUPPORTED_TYPES = {
    "string",
    "int",
    "float",
    "boolean"
}

def load_schema(schema_path):
    with open(schema_path, "r") as schema_file:
        try:
            schema = json.load(schema_file)
        except json.JSONDecodeError:
            raise ValueError(
                "Schema file contains invalid JSON."
            )

    return validate_schema_structure(schema)


def validate_schema_structure(schema):
    if "columns" not in schema:
        raise ValueError("Schema must contain 'columns' key.")
    
    for col_name, col_config in schema["columns"].items():
        if "type" not in col_config or "required" not in col_config:
            raise ValueError(
                f"Column '{col_name}' must contain both 'type' and 'required'."
            )
        if col_config["type"] not in SUPPORTED_TYPES:
            raise ValueError(f"Unsupported type '{col_config['type']}' in schema.")
        if not isinstance(col_config["required"], bool):
            raise ValueError(
                f"Column '{col_name}' has invalid 'required' value."
            )
            
    return schema["columns"]
