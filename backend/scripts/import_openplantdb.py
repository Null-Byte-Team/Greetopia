"""Import OpenPlantDB's CC0 garden-plant dataset into Greetopia's local SQLite catalog.

Usage from the backend directory:
  python scripts/import_openplantdb.py --download
  python scripts/import_openplantdb.py --file data/external/openplantdb_plants.json

The source dataset is large, so it is not bundled wholesale. Greetopia ships an offline
starter catalog and this importer for installations with network access.
"""
from __future__ import annotations
import argparse, json, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.core.config import settings  # noqa: E402
from app.db.database import init_db, db_session  # noqa: E402

SOURCE_URL = 'https://raw.githubusercontent.com/cwfrazier1/openplantdb/main/data/plants.json'


def load_records(path: Path):
    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get('plants', list(data.values()))
    if not isinstance(data, list):
        raise ValueError('Expected OpenPlantDB JSON to contain a list of plant records.')
    return [x for x in data if isinstance(x, dict) and x.get('slug')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true', help='Download the current upstream JSON dataset first')
    parser.add_argument('--file', type=Path, default=BACKEND/'data'/'external'/'openplantdb_plants.json')
    args = parser.parse_args()
    path = args.file if args.file.is_absolute() else (Path.cwd()/args.file).resolve()
    if args.download:
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(SOURCE_URL, headers={'User-Agent':'Greetopia-prototype-dataset-import/1.0'})
        with urllib.request.urlopen(request, timeout=90) as response, path.open('wb') as output:
            while True:
                chunk = response.read(1024*1024)
                if not chunk: break
                output.write(chunk)
        print(f'Downloaded upstream dataset to {path}')
    if not path.is_file():
        raise SystemExit(f'Dataset not found: {path}. Run with --download or supply --file.')
    records = load_records(path)
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with db_session() as db:
        for record in records:
            slug = str(record['slug'])[:160]
            common = str(record.get('common_name') or record.get('name') or slug.replace('-', ' ').title())[:200]
            scientific = str(record.get('scientific_name') or '')[:250]
            category = str(record.get('category') or record.get('subcategory') or 'unknown')[:100]
            aliases = record.get('aliases') or []
            if not isinstance(aliases, list): aliases = [str(aliases)]
            db.execute('''INSERT INTO plant_knowledge(slug,common_name,scientific_name,category,aliases_json,data_json,source_name,source_url,license,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET common_name=excluded.common_name, scientific_name=excluded.scientific_name, category=excluded.category, aliases_json=excluded.aliases_json, data_json=excluded.data_json, source_name=excluded.source_name, source_url=excluded.source_url, license=excluded.license, updated_at=excluded.updated_at''',
                (slug, common, scientific, category, json.dumps(aliases, ensure_ascii=False), json.dumps(record, ensure_ascii=False), 'OpenPlantDB', 'https://github.com/cwfrazier1/openplantdb', 'CC0-1.0', now))
    print(f'Imported/updated {len(records)} OpenPlantDB records into {settings.database_path}')

if __name__ == '__main__':
    main()
