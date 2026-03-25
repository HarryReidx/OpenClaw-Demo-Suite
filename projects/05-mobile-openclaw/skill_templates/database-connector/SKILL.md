---
name: "database-connector"
description: "Connect to relational databases and inspect schemas or run read-only SQL checks. Use when the task involves validating connectivity to SQLite, MySQL, or PostgreSQL, listing tables, or running smoke-test queries before integrating application code."
---

# Database Connector

## Workflow
1. Confirm the target database type and connection details before querying.
2. Prefer a smoke test first: connect, run `SELECT 1`, then list schemas or tables.
3. Default to read-only inspection unless the user explicitly asks for writes.
4. Capture connection errors verbatim and report the failing host, port, or driver.

## Supported paths
- SQLite: use Python `sqlite3`.
- MySQL: use `pymysql` if available.
- PostgreSQL: use `psycopg` or `psycopg2` if available.

## Smoke testing
Use the bundled script for a deterministic connectivity check:

```bash
python scripts/smoke_test.py --database sqlite --path /path/to/file.db
```

The script creates a demo table when needed, runs `SELECT 1`, and prints a short success summary.

## Output expectations
- State the database type.
- Confirm whether the connection succeeded.
- Include the smoke-test query result.
- Include the discovered tables when available.
