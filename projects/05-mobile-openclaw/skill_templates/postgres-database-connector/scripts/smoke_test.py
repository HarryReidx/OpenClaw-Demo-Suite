from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="postgresql")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", default="5432")
    parser.add_argument("--user", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--database-name", dest="database_name", default="")
    parser.add_argument("--database_name", dest="database_name", default="")
    args = parser.parse_args()

    payload = {
        "ok": True,
        "database": "postgresql",
        "mode": "package-check",
        "probe": 1,
        "tables": [],
    }

    if args.host and args.user and args.database_name:
        try:
            try:
                import psycopg
                use_psycopg2 = False
            except ImportError:
                import psycopg2 as psycopg
                use_psycopg2 = True

            connection = psycopg.connect(
                host=args.host,
                port=int(args.port or 5432),
                user=args.user,
                password=args.password,
                dbname=args.database_name,
            )
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    probe = cursor.fetchone()
                    cursor.execute(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                        ORDER BY table_name
                        """
                    )
                    tables = cursor.fetchall()
                payload.update(
                    {
                        "mode": "live-connection",
                        "driver": "psycopg2" if use_psycopg2 else "psycopg",
                        "probe": probe[0] if probe else 1,
                        "tables": [row[0] for row in tables],
                        "host": args.host,
                        "database_name": args.database_name,
                    }
                )
            finally:
                connection.close()
        except Exception as exc:
            payload.update({"ok": False, "error": str(exc)})
    else:
        payload["note"] = "No PostgreSQL connection info provided; installed package validated only."

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
