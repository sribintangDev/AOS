from __future__ import annotations

from collections.abc import Generator
import os
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SQLITE_DATABASE_URL = f"sqlite:///{DATA_DIR / 'aos_training.db'}"
DEFAULT_SUPABASE_POOLER_HOST = "aws-1-ap-northeast-1.pooler.supabase.com"


def supabase_pooler_host() -> str:
    return (
        os.getenv("AOS_TRAINING_SUPABASE_POOLER_HOST")
        or os.getenv("SUPABASE_POOLER_HOST")
        or DEFAULT_SUPABASE_POOLER_HOST
    )


def normalize_database_url(url: str) -> str:
    url = url.strip().strip("\"'")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if url.startswith("postgresql+psycopg://"):
        parsed = urlsplit(url)
        if parsed.hostname and parsed.hostname.startswith("db.") and parsed.hostname.endswith(".supabase.co"):
            ref = parsed.hostname[3 : -len(".supabase.co")]
            username = parsed.username or "postgres"
            if username == "postgres":
                username = f"postgres.{ref}"
            password = parsed.password or ""
            netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{supabase_pooler_host()}:6543"
            url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
            parsed = urlsplit(url)
        elif parsed.hostname and parsed.hostname == "aws-0-ap-northeast-1.pooler.supabase.com":
            netloc = parsed.netloc.replace("aws-0-ap-northeast-1.pooler.supabase.com", supabase_pooler_host())
            url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
            parsed = urlsplit(url)
        if "sslmode=" not in url:
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query["sslmode"] = "require"
            url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    return url


DATABASE_URL = normalize_database_url(
    os.getenv("AOS_TRAINING_DATABASE_URL")
    or os.getenv("SUPABASE_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or os.getenv("SUPABASE_DB_URL")
    or os.getenv("POSTGRES_URL")
    or SQLITE_DATABASE_URL
)

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {"prepare_threshold": None}
)

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
