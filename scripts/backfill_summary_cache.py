import lancedb
import hashlib
import json
from pathlib import Path
from typing import Optional
from mcp_plesk_dev_docs.settings import settings


def get_file_hash(file_path: Path) -> str:
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_file(filename: str, category: str) -> Optional[Path]:
    """Finds the file on disk using pure Python rglob."""
    kb_root = Path("knowledge_base")

    # Try direct mapping first for efficiency
    category_map = {
        "guide": "extensions-guide",
        "cli": "cli-linux",
        "api": "api-rpc",
        "js-sdk": "sdk",
        "php-stubs": "stubs",
    }
    dir_name = category_map.get(category, category)
    search_root = kb_root / dir_name

    if not search_root.exists():
        search_root = kb_root

    try:
        # Use rglob to find the file
        for p in search_root.rglob(filename):
            return p
    except Exception:
        pass

    return None


def backfill_cache():
    db_path = Path(f"storage/lancedb_{settings.plesk_model_profile}")
    if not db_path.exists():
        print(f"Database {db_path} not found.")
        return

    db = lancedb.connect(db_path)
    table_name = "plesk_knowledge"
    # No check needed as we verified it manually
    table = db.open_table(table_name)
    # Get unique filenames and their summaries
    data = (
        table.search()
        .select(["filename", "category", "summary"])
        .limit(100000)
        .to_list()
    )
    print(f"Total rows retrieved: {len(data)}")

    cache = {}

    count = 0
    seen_files = set()
    for row in data:
        filename = row["filename"]
        category = row["category"]
        summary = row.get("summary")

        file_key = f"{category}/{filename}"
        if file_key in seen_files:
            continue
        seen_files.add(file_key)

        if not summary or summary == "Description unavailable.":
            continue

        file_path = find_file(filename, category)

        if file_path:
            f_hash = get_file_hash(file_path)
            if f_hash not in cache:
                cache[f_hash] = summary
                count += 1
        else:
            # print(f"File not found on disk: {category}/{filename}")
            pass

    with open("storage/summaries_cache.json", "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"Successfully backfilled {count} summaries into cache.")


if __name__ == "__main__":
    backfill_cache()
