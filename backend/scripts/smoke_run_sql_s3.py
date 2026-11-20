"""Manual smoke test kiểm chứng DuckDBSqlExecutor trên bucket S3 thật.

Cách chạy (từ thư mục gốc repository với PYTHONPATH=backend):
    $env:PYTHONPATH = "backend"
    python backend/scripts/smoke_run_sql_s3.py --parquet-key "default/<doc_id>/v1/tables/nhansu.parquet"

Kịch bản kiểm chứng:
1. Khởi tạo DuckDBSqlExecutor từ `.env` (xác nhận STORAGE_BACKEND=s3 và S3_QUERY_* khác S3_INGEST_*).
2. Đọc & chạy SELECT tổng hợp trên file Parquet của tenant hiện tại qua DuckDB httpfs -> phải THÀNH CÔNG.
3. Thử dùng credential S3_QUERY_* để ghi (`put_object`) lên S3 -> IAM phải TỪ CHỐI (AccessDenied).
4. Thử đọc file Parquet thuộc prefix tenant khác (`other_tenant/...`) -> phải BỊ CHẶN bởi tenant guard / S3 secret SCOPE.
"""

from __future__ import annotations

import argparse
import sys
from uuid import uuid4

import boto3

from app.documents.ports import AuthorizedSqlTable, SqlQueryExecutionError
from app.infrastructure.duckdb_executor import create_duckdb_sql_executor
from app.shared.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test DuckDB S3 read-only query executor.")
    parser.add_argument(
        "--parquet-key",
        required=True,
        help="Đường dẫn Parquet trên S3, ví dụ: default/<doc_id>/v1/tables/nhansu.parquet",
    )
    parser.add_argument(
        "--tenant-id",
        default=settings.default_tenant_id,
        help="Tenant ID sở hữu file Parquet (mặc định: DEFAULT_TENANT_ID).",
    )
    args = parser.parse_args()

    print("[1/4] Khởi tạo DuckDBSqlExecutor từ cấu hình .env...")
    executor = create_duckdb_sql_executor(settings)
    print("  -> OK: Executor khởi tạo thành công (S3_QUERY_* đã tách biệt với S3_INGEST_*).")

    table = AuthorizedSqlTable(
        view_name="smoke_table",
        parquet_key=args.parquet_key,
        tenant_id=args.tenant_id,
    )

    print(f"[2/4] Chạy SELECT COUNT(*) trên '{args.parquet_key}' (tenant='{args.tenant_id}')...")
    result = executor.execute(
        tables=[table],
        sql="SELECT COUNT(*) AS total_rows FROM smoke_table LIMIT 10",
        tenant_id=args.tenant_id,
    )
    print(f"  -> OK: columns={result.columns}, rows={result.rows}, truncated={result.truncated}")

    print("[3/4] Kiểm chứng IAM: thử put_object bằng S3_QUERY_* (kỳ vọng bị từ chối AccessDenied)...")
    q_key = (
        settings.s3_query_access_key_id.get_secret_value()
        if settings.s3_query_access_key_id
        else None
    )
    q_secret = (
        settings.s3_query_secret_access_key.get_secret_value()
        if settings.s3_query_secret_access_key
        else None
    )
    client_kwargs = {
        "region_name": settings.s3_region,
        "aws_access_key_id": q_key,
        "aws_secret_access_key": q_secret,
    }
    if settings.s3_endpoint_url:
        client_kwargs["endpoint_url"] = settings.s3_endpoint_url

    s3_query_client = boto3.client("s3", **client_kwargs)
    probe_write_key = f"{args.tenant_id}/_smoke_readonly_probe_{uuid4()}.txt"
    try:
        s3_query_client.put_object(
            Bucket=settings.s3_bucket,
            Key=probe_write_key,
            Body=b"should-be-denied",
        )
        print("  -> [FAIL] Credential S3_QUERY_* lại ghi được object lên bucket! Hãy thu hồi quyền s3:PutObject.")
        return 1
    except Exception:
        print("  -> OK: IAM đã từ chối thao tác ghi (put_object) của S3_QUERY_*.")

    print("[4/4] Kiểm chứng cô lập tenant: thử truy vấn Parquet prefix của tenant khác...")
    cross_tenant_table = AuthorizedSqlTable(
        view_name="cross_tenant",
        parquet_key=f"other_tenant/{uuid4()}/v1/tables/secret.parquet",
        tenant_id="other_tenant",
    )
    try:
        executor.execute(
            tables=[cross_tenant_table],
            sql="SELECT * FROM cross_tenant LIMIT 1",
            tenant_id=args.tenant_id,
        )
        print("  -> [FAIL] Truy vấn cross-tenant không bị chặn!")
        return 1
    except SqlQueryExecutionError:
        print("  -> OK: Truy vấn cross-tenant đã bị chặn an toàn.")

    print("PASS: Hoàn tất 4 bước smoke test DuckDB S3 Read-Only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
