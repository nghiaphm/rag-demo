"""Safe, idempotent Demo Workspace seed script (--dry-run by default, zero PII).

Safety invariants:
1. Defaults to dry-run (`--dry-run` unless `--apply` is explicitly passed): validates
   every synthetic sample file, reads SHA-256 checksums and `.xlsx` safety bounds
   (`read_workbook`), and prints planned operations without opening MongoDB/Qdrant
   or writing storage.
2. Enforces isolation from primary application data: defaults target Qdrant collection
   `rag_documents_demo` and local storage `./data/documents_demo`. Writing to `rag_documents`
   or primary `./data/documents` is blocked unless `--allow-primary-collection` is explicitly set.
3. Uses only 100% synthetic/public technical fixtures (zero real HR PII).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.documents.excel.validation import WorkbookError, read_workbook
from app.documents.indexes import initialize_document_indexes
from app.documents.ingestion import IngestionService
from app.documents.migrations.demo_corpus import DemoCorpusMigration, MigrationSource
from app.documents.repository import MongoDocumentRepository
from app.infrastructure.connections import CloudConnections
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.infrastructure.storage import create_file_storage
from app.rag.embeddings import get_embeddings
from app.shared.config import Settings, settings


DEFAULT_DEMO_COLLECTION = "rag_documents_demo"
DEFAULT_DEMO_DB_NAME = "rag_demo_workspace"
DEFAULT_DEMO_DOCUMENTS_DIR = "./data/documents_demo"
PRIMARY_PRODUCTION_COLLECTION = "rag_documents"
PRIMARY_DOCUMENTS_DIR = (PROJECT_ROOT / "data" / "documents").resolve()


@dataclass(frozen=True, slots=True)
class DemoFixtureSpec:
    source_key: str
    relative_path: str
    category: str
    contains_pii: bool = False


DEMO_FIXTURE_SPECS: tuple[DemoFixtureSpec, ...] = (
    DemoFixtureSpec(
        source_key="demo-ws:hr-employees-mock",
        relative_path="data/hr_employees_mock.xlsx",
        category="synthetic_excel_hr",
    ),
    DemoFixtureSpec(
        source_key="demo-ws:hr-leave-policy",
        relative_path="backend/evaluation/datasets/corpus/hr-leave-policy.md",
        category="synthetic_hr_policy",
    ),
    DemoFixtureSpec(
        source_key="demo-ws:security-incident-sop",
        relative_path="backend/evaluation/datasets/corpus/security-incident-sop.txt",
        category="synthetic_security_sop",
    ),
    DemoFixtureSpec(
        source_key="demo-ws:enterprise-it-kb",
        relative_path="data/prompt/enterprise_it_knowledge_base.xlsx",
        category="synthetic_excel_it_kb",
    ),
    DemoFixtureSpec(
        source_key="demo-ws:qdrant-architecture",
        relative_path="backend/evaluation/datasets/corpus/qdrant.md",
        category="technical_architecture",
    ),
    DemoFixtureSpec(
        source_key="demo-ws:chunking-spec",
        relative_path="backend/evaluation/datasets/corpus/chunking.md",
        category="technical_architecture",
    ),
    DemoFixtureSpec(
        source_key="demo-ws:embedding-spec",
        relative_path="backend/evaluation/datasets/corpus/llm-embedding.md",
        category="technical_architecture",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedSeedItem:
    source_key: str
    file_name: str
    path: Path
    category: str
    size_bytes: int
    checksum_sha256: str


def validate_demo_target(
    qdrant_collection: str,
    *,
    documents_dir: str | Path = DEFAULT_DEMO_DOCUMENTS_DIR,
    allow_primary_collection: bool = False,
) -> tuple[str, Path]:
    """Ensure the seed script does not overwrite primary `rag_documents` by accident."""
    normalized_collection = (qdrant_collection or "").strip()
    if not normalized_collection:
        raise ValueError("Target Qdrant collection name must not be empty.")

    raw_dir = Path(documents_dir)
    resolved_dir = raw_dir.resolve() if raw_dir.is_absolute() else (PROJECT_ROOT / raw_dir).resolve()

    if not allow_primary_collection:
        if normalized_collection.lower() == PRIMARY_PRODUCTION_COLLECTION:
            raise ValueError(
                "Refusing to target primary collection 'rag_documents' without "
                "--allow-primary-collection. Use 'rag_documents_demo' for safe demo seeding."
            )
        if resolved_dir == PRIMARY_DOCUMENTS_DIR:
            raise ValueError(
                f"Refusing to target primary documents directory '{resolved_dir}' without "
                "--allow-primary-collection. Use './data/documents_demo' instead."
            )

    return normalized_collection, resolved_dir


def validate_demo_fixtures(
    specs: tuple[DemoFixtureSpec, ...] = DEMO_FIXTURE_SPECS,
    *,
    repo_root: Path = PROJECT_ROOT,
) -> list[ValidatedSeedItem]:
    """Read-only validation of all synthetic fixture files (existence, checksum, XLSX safety)."""
    items: list[ValidatedSeedItem] = []
    seen_keys: set[str] = set()

    for spec in specs:
        if spec.contains_pii:
            raise ValueError(f"Refusing fixture marked as containing PII: {spec.source_key}")
        if spec.source_key in seen_keys:
            raise ValueError(f"Duplicate demo source_key: {spec.source_key}")
        seen_keys.add(spec.source_key)

        file_path = (repo_root / spec.relative_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Missing demo fixture file: {spec.relative_path}")

        content = file_path.read_bytes()
        if not content:
            raise ValueError(f"Demo fixture file is empty: {spec.relative_path}")

        if file_path.suffix.lower() == ".xlsx":
            try:
                read_workbook(content)
            except WorkbookError as exc:
                raise ValueError(
                    f"Demo XLSX fixture failed safety validation ({spec.relative_path}): {exc}"
                ) from exc

        items.append(
            ValidatedSeedItem(
                source_key=spec.source_key,
                file_name=file_path.name,
                path=file_path,
                category=spec.category,
                size_bytes=len(content),
                checksum_sha256=hashlib.sha256(content).hexdigest(),
            )
        )

    return items


def run_dry_run_plan(
    *,
    qdrant_collection: str = DEFAULT_DEMO_COLLECTION,
    mongodb_db_name: str = DEFAULT_DEMO_DB_NAME,
    documents_dir: str = DEFAULT_DEMO_DOCUMENTS_DIR,
    allow_primary_collection: bool = False,
) -> dict[str, Any]:
    """Validate target isolation and synthetic fixtures with zero external I/O."""
    safe_collection, resolved_dir = validate_demo_target(
        qdrant_collection,
        documents_dir=documents_dir,
        allow_primary_collection=allow_primary_collection,
    )
    validated_items = validate_demo_fixtures()
    return {
        "mode": "dry_run",
        "applied": False,
        "target": {
            "qdrant_collection": safe_collection,
            "mongodb_db_name": mongodb_db_name.strip() or DEFAULT_DEMO_DB_NAME,
            "documents_dir": str(resolved_dir),
        },
        "total_fixtures": len(validated_items),
        "items": [
            {
                "source_key": item.source_key,
                "file_name": item.file_name,
                "category": item.category,
                "size_bytes": item.size_bytes,
                "checksum_sha256": item.checksum_sha256,
                "planned_action": "CREATE_OR_VERIFY_IDEMPOTENT",
            }
            for item in validated_items
        ],
    }


def apply_demo_seed(
    *,
    qdrant_collection: str = DEFAULT_DEMO_COLLECTION,
    mongodb_db_name: str = DEFAULT_DEMO_DB_NAME,
    documents_dir: str = DEFAULT_DEMO_DOCUMENTS_DIR,
    allow_primary_collection: bool = False,
) -> dict[str, Any]:
    """Execute idempotent demo ingestion into isolated MongoDB, Qdrant, and storage targets."""
    safe_collection, resolved_dir = validate_demo_target(
        qdrant_collection,
        documents_dir=documents_dir,
        allow_primary_collection=allow_primary_collection,
    )
    validated_items = validate_demo_fixtures()
    sources = [MigrationSource(item.source_key, item.path) for item in validated_items]

    demo_settings = Settings(
        groq_api_key=settings.groq_api_key,
        openai_base_url=settings.openai_base_url,
        llm_model=settings.llm_model,
        embedding_provider=settings.embedding_provider,
        embedding_api_key=settings.embedding_api_key,
        embedding_model=settings.embedding_model,
        mongodb_uri=settings.mongodb_uri,
        mongodb_db_name=(mongodb_db_name.strip() or DEFAULT_DEMO_DB_NAME),
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        qdrant_collection=safe_collection,
        qdrant_allow_insecure_http=settings.qdrant_allow_insecure_http,
        documents_dir=str(resolved_dir),
        storage_backend="local",
        excel_parquet_ingestion_enabled=True,
    )

    connections = CloudConnections(demo_settings)
    try:
        statuses = connections.connect_all()
        if not statuses["mongodb"].ok or not statuses["qdrant"].ok:
            raise RuntimeError(
                "Cloud dependencies are not ready for demo seed "
                f"(mongodb={statuses['mongodb'].code}, qdrant={statuses['qdrant'].code})."
            )
        database = connections.mongodb.database
        qdrant_client = connections.qdrant.client
        if database is None or qdrant_client is None:
            raise RuntimeError("Missing MongoDB or Qdrant client handle.")

        resolved_dir.mkdir(parents=True, exist_ok=True)
        initialize_document_indexes(database)
        repository = MongoDocumentRepository(database)
        storage = create_file_storage(demo_settings)
        vector_index = QdrantVectorIndex(qdrant_client, safe_collection)
        embeddings = get_embeddings()

        with (
            patch.object(settings, "qdrant_collection", safe_collection),
            patch.object(settings, "storage_backend", "local"),
            patch.object(settings, "documents_dir", str(resolved_dir)),
        ):
            ingestion = IngestionService(
                repository=repository,
                storage=storage,
                vector_index=vector_index,
                embeddings=embeddings,
                embedding_model=demo_settings.embedding_model,
                parquet_ingestion_enabled=True,
            )
            migration = DemoCorpusMigration(
                repository=repository,
                storage=storage,
                vector_index=vector_index,
                ingestion=ingestion,
                embeddings=embeddings,
            )
            summary = migration.migrate(sources)

        return {
            "mode": "apply",
            "applied": True,
            "target": {
                "qdrant_collection": safe_collection,
                "mongodb_db_name": demo_settings.mongodb_db_name,
                "documents_dir": str(resolved_dir),
            },
            "summary": {
                "created": summary.created,
                "updated": summary.updated,
                "verified": summary.verified,
                "failed": summary.failed,
            },
            "items": [
                {
                    "source_key": item.source_key,
                    "file_name": item.file_name,
                    "outcome": item.outcome,
                    "document_id": item.document_id,
                    "version_id": item.version_id,
                    "chunk_count": item.chunk_count,
                    "error_code": item.error_code,
                }
                for item in summary.items
            ],
        }
    finally:
        connections.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Safe, idempotent RAG Workspace Demo seed script (--dry-run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute actual MongoDB, Qdrant, and storage ingestion. Without --apply, runs in --dry-run mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly validate fixtures and print planned operations without side effects (default).",
    )
    parser.add_argument(
        "--qdrant-collection",
        default=DEFAULT_DEMO_COLLECTION,
        help=f"Isolated Qdrant collection for demo data (default: {DEFAULT_DEMO_COLLECTION}).",
    )
    parser.add_argument(
        "--mongodb-db-name",
        default=DEFAULT_DEMO_DB_NAME,
        help=f"Isolated MongoDB database name for demo data (default: {DEFAULT_DEMO_DB_NAME}).",
    )
    parser.add_argument(
        "--documents-dir",
        default=DEFAULT_DEMO_DOCUMENTS_DIR,
        help=f"Isolated local storage directory (default: {DEFAULT_DEMO_DOCUMENTS_DIR}).",
    )
    parser.add_argument(
        "--allow-primary-collection",
        action="store_true",
        help="Explicit safeguard bypass permitting writes to primary 'rag_documents' or './data/documents'.",
    )
    args = parser.parse_args(argv)

    if args.apply and args.dry_run:
        print("BLOCKED: Choose either --dry-run (default) or --apply, not both.", file=sys.stderr)
        return 2

    try:
        if not args.apply:
            plan = run_dry_run_plan(
                qdrant_collection=args.qdrant_collection,
                mongodb_db_name=args.mongodb_db_name,
                documents_dir=args.documents_dir,
                allow_primary_collection=args.allow_primary_collection,
            )
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0

        result = apply_demo_seed(
            qdrant_collection=args.qdrant_collection,
            mongodb_db_name=args.mongodb_db_name,
            documents_dir=args.documents_dir,
            allow_primary_collection=args.allow_primary_collection,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["summary"]["failed"] == 0 else 1
    except (ValueError, FileNotFoundError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
