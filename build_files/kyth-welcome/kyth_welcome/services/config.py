import logging
import os
import json
import tempfile

_logger = logging.getLogger(__name__)

def load_json_config(path: str, default=None) -> dict:
    """Safely loads a JSON configuration file. Returns default if file does not exist or is invalid."""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        _logger.warning("load_json_config: %s is unreadable or invalid — using defaults", path, exc_info=True)
    return default if default is not None else {}

def save_json_config(path: str, data: dict, mode: int = None) -> bool:
    """Saves a JSON configuration file atomically (write to temp file, then rename/replace)."""
    try:
        dir_name = os.path.dirname(path)
        os.makedirs(dir_name, exist_ok=True)
        # Use tempfile to write atomically
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            temp_path = f.name
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        return True
    except Exception:
        return False
