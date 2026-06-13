from __future__ import annotations

import os
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

from app.database import DATABASE_URL, normalize_database_url


def masked(value: str | None, keep_start: int = 2, keep_end: int = 2) -> str:
    if not value:
        return "(missing)"
    if len(value) <= keep_start + keep_end:
        return "*" * len(value)
    return f"{value[:keep_start]}***{value[-keep_end:]}"


def main() -> None:
    raw = (
        os.getenv("AOS_TRAINING_DATABASE_URL")
        or os.getenv("SUPABASE_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("POSTGRES_URL")
        or ""
    )
    if not raw:
        print("No Postgres database secret found. The module will use SQLite.")
        return

    normalized = normalize_database_url(raw)
    parsed = urlsplit(normalized)
    password = parsed.password or ""
    print("Database URL present: yes")
    print(f"Scheme: {parsed.scheme}")
    print(f"Host: {parsed.hostname or '(missing)'}")
    print(f"Port: {parsed.port or '(default)'}")
    print(f"Username: {parsed.username or '(missing)'}")
    print(f"Password present: {bool(password)}")
    print(f"Password preview: {masked(password)}")
    print(f"Database path: {parsed.path or '(missing)'}")
    print(f"Query: {parsed.query or '(none)'}")
    if "YOUR-PASSWORD" in password or "[YOUR" in password or "<YOUR" in password:
        print("Problem: password placeholder still appears to be in the connection string.")
    if parsed.hostname and parsed.hostname.startswith("db."):
        print("Note: direct Supabase DB host was not rewritten. On Replit, the pooler host is usually safer.")

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        print("Database test:", conn.execute(text("select 1")).scalar_one())


if __name__ == "__main__":
    main()
