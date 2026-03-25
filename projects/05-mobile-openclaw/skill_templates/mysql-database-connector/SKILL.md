---
name: "mysql-database-connector"
description: "Connect to MySQL databases and run read-only SQL checks."
---

# MySQL Database Connector

## Workflow
1. Confirm host, port, user, password, and database before querying.
2. Prefer a smoke test first: connect, run `SELECT 1`, then list tables.
3. Default to read-only inspection unless the user explicitly asks for writes.
4. If connection info is missing, explain which fields are still needed.

## Supported access
- Connection URL: `mysql://user:password@host:3306/database`
- Named fields: `host=... port=... user=... password=... database=...`

## Output expectations
- State the database type.
- Confirm whether connection succeeded.
- Include the smoke-test result.
- Include discovered tables when available.
