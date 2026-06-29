import hashlib


def generate_file_hash(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(4096):
            hasher.update(chunk)
    return hasher.hexdigest()


def generate_combined_hash(file_hash: str, schema_hash: str) -> str:
    combined = file_hash + schema_hash
    return hashlib.sha256(combined.encode()).hexdigest()