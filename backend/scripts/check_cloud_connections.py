"""Smoke test chỉ-đọc cho MongoDB Atlas và Qdrant Cloud.

Không in URI, database name, API key hoặc raw exception.
Exit code 0 chỉ khi cả hai dịch vụ kết nối/xác thực thành công.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.cloud_connections import CloudConnections


def main() -> int:
    connections = CloudConnections()
    try:
        statuses = connections.connect_all()
        for name, status in statuses.items():
            print(f"{name}: ok={status.ok}; code={status.code}; message={status.message}")
        return 0 if all(status.ok for status in statuses.values()) else 1
    finally:
        connections.close()


if __name__ == "__main__":
    raise SystemExit(main())
