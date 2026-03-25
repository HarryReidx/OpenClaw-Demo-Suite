---
name: "postgres-database-connector"
description: "Connect to PostgreSQL databases and run read-only SQL checks."
---

# PostgreSQL Database Connector

## Workflow
1. Confirm host, port, user, password, and database before querying.
2. Prefer a smoke test first: connect, run `SELECT 1`, then list tables.
3. Default to read-only inspection unless the user explicitly asks for writes.
4. If connection info is missing, explain which fields are still needed.

## Supported access
- Connection URL: `postgresql://user:password@host:5432/database`
- Named fields: `host=... port=... user=... password=... database=...`

## Output expectations
- State the database type.
- Confirm whether connection succeeded.
- Include the smoke-test result.
- Include discovered tables when available.
