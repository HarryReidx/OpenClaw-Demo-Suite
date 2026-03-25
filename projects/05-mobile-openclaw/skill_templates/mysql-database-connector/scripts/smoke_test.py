from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="mysql")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", default="3306")
    parser.add_argument("--user", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--database-name", dest="database_name", default="")
    parser.add_argument("--database_name", dest="database_name", default="")
    args = parser.parse_args()

    payload = {
        "ok": True,
        "database": "mysql",
        "mode": "package-check",
        "probe": 1,
        "tables": [],
    }

    if args.host and args.user and args.database_name:
        try:
            import pymysql
            from pymysql.cursors import DictCursor

            connection = pymysql.connect(
                host=args.host,
                port=int(args.port or 3306),
                user=args.user,
                password=args.password,
                database=args.database_name,
                cursorclass=DictCursor,
                autocommit=True,
            )
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 AS probe")
                    row = cursor.fetchone() or {}
                    cursor.execute("SHOW TABLES")
                    tables = cursor.fetchall()
                payload.update(
                    {
                        "mode": "live-connection",
                        "probe": row.get("probe", 1),
                        "tables": [next(iter(item.values())) for item in tables],
                        "host": args.host,
                        "database_name": args.database_name,
                    }
                )
            finally:
                connection.close()
        except Exception as exc:
            payload.update({"ok": False, "error": str(exc)})
    else:
        payload["note"] = "No MySQL connection info provided; installed package validated only."

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
