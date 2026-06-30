import json
import re

SUPPORTED_TYPES = {
    "string",
    "int",
    "float",
    "boolean"
}

SUPPORTED_CROSS_FIELD_RULE_TYPES = {
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "not_equal",
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

        if "pattern" in col_config:
            if not isinstance(col_config["pattern"], str):
                raise ValueError(
                    f"Column '{col_name}' has invalid 'pattern' value; must be a string."
                )
            try:
                re.compile(col_config["pattern"])
            except re.error as e:
                raise ValueError(
                    f"Column '{col_name}' has invalid regex pattern: {e}"
                )

        if "min" in col_config and not isinstance(col_config["min"], (int, float)):
            raise ValueError(
                f"Column '{col_name}' has invalid 'min' value; must be numeric."
            )

        if "max" in col_config and not isinstance(col_config["max"], (int, float)):
            raise ValueError(
                f"Column '{col_name}' has invalid 'max' value; must be numeric."
            )

        if "min" in col_config and "max" in col_config and col_config["min"] > col_config["max"]:
            raise ValueError(
                f"Column '{col_name}' has 'min' greater than 'max'."
            )

        if "unique" in col_config and not isinstance(col_config["unique"], bool):
            raise ValueError(
                f"Column '{col_name}' has invalid 'unique' value; must be a boolean."
            )

    cross_field_rules = validate_cross_field_rules_structure(
        schema.get("cross_field_rules", []),
        schema["columns"]
    )

    return {
        "columns": schema["columns"],
        "cross_field_rules": cross_field_rules,
    }


def validate_cross_field_rules_structure(cross_field_rules, columns):
    if not isinstance(cross_field_rules, list):
        raise ValueError("'cross_field_rules' must be a list.")

    for i, rule in enumerate(cross_field_rules):
        if "type" not in rule or "field" not in rule or "than" not in rule:
            raise ValueError(
                f"cross_field_rules[{i}] must contain 'type', 'field', and 'than'."
            )

        if rule["type"] not in SUPPORTED_CROSS_FIELD_RULE_TYPES:
            raise ValueError(
                f"cross_field_rules[{i}] has unsupported type '{rule['type']}'."
            )

        if rule["field"] not in columns:
            raise ValueError(
                f"cross_field_rules[{i}] references unknown column '{rule['field']}'."
            )

        if rule["than"] not in columns:
            raise ValueError(
                f"cross_field_rules[{i}] references unknown column '{rule['than']}'."
            )

        if rule["field"] == rule["than"]:
            raise ValueError(
                f"cross_field_rules[{i}] cannot compare column '{rule['field']}' to itself."
            )

    return cross_field_rules