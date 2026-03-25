from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def run_sqlite_test(path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        cursor = connection.cursor()
        cursor.execute("create table if not exists healthcheck (id integer primary key, note text)")
        cursor.execute("insert into healthcheck(note) values ('ok')")
        cursor.execute("select 1")
        probe = cursor.fetchone()
        cursor.execute("select name from sqlite_master where type='table' order by name")
        tables = [row[0] for row in cursor.fetchall()]
        connection.commit()
        return {
            "ok": True,
            "database": "sqlite",
            "path": str(path),
            "probe": probe[0] if probe else None,
            "tables": tables,
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", choices=["sqlite"], default="sqlite")
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    if args.database != "sqlite":
        raise SystemExit("Only sqlite smoke tests are bundled in this demo skill.")

    result = run_sqlite_test(Path(args.path))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
