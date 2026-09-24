"""Kết nối PostgreSQL + pgvector.

- `get_engine()`: `PGEngine` của langchain-postgres dùng cho vector store.
- `get_sync_engine()`: SQLAlchemy Engine đồng bộ dùng cho kiểm tra nhẹ (table tồn tại).
- `table_exists()`: kiểm tra table đã tồn tại chưa.

Mọi thông số lấy từ `settings.database_url`; không hard-code.
"""

import asyncio
import sys
from functools import lru_cache

from langchain_postgres import PGEngine
from sqlalchemy import Engine, create_engine, text

from app.config import settings

if sys.platform == "win32":
    # psycopg async (được langchain-postgres dùng) không chạy trên ProactorEventLoop
    # mặc định của Windows; phải dùng SelectorEventLoop.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@lru_cache
def get_engine() -> PGEngine:
    """Trả về `PGEngine` dùng chung cho vector store (khởi tạo đúng 1 lần)."""
    return PGEngine.from_connection_string(url=settings.database_url)


@lru_cache
def get_sync_engine() -> Engine:
    """Trả về SQLAlchemy `Engine` đồng bộ dùng cho query kiểm tra."""
    return create_engine(settings.database_url)


def table_exists(table_name: str, schema_name: str = "public") -> bool:
    """Kiểm tra `table_name` đã tồn tại trong database hay chưa."""
    statement = text("SELECT to_regclass(:qualified_name)")
    qualified_name = f"{schema_name}.{table_name}"
    with get_sync_engine().connect() as connection:
        return connection.execute(statement, {"qualified_name": qualified_name}).scalar() is not None
