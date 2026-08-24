# Database Layer

This folder contains database-owned project components that are intentionally separate from the FastAPI backend source.

- `database.py` opens SQLite connections, owns schema creation, and runs idempotent migrations.
- `models/` contains database-facing model and account data operations.
- `schemas.py` is reserved for shared database schema helpers.
- `migrations/` is reserved for future standalone migration files.
- `seeds/` is reserved for future seed data.
- `data/` stores local SQLite databases and uploaded files during development.

The backend imports this layer through `db.database` and `db.models`.