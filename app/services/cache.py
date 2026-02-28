import json
import os


CACHE_DIR = "data/cache"


def get_cache_path(domain: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe_name = domain.replace(".", "_")
    return os.path.join(CACHE_DIR, f"{safe_name}.json")


def load_from_cache(domain: str):
    path = get_cache_path(domain)

    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_to_cache(domain: str, data: dict):
    path = get_cache_path(domain)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)