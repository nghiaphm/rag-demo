"""Opt-in F8-02 runner. Default is plan-only: no network/provider/mutation.

Only this process's fresh namespaces may be removed. Never use this against an
existing corpus. Provider HTTP attempts are counted before send, retries off.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


class ProviderBudget:
    def __init__(self, path, groq=5, gemini=4):
        self.path = path
        self.limits = {"groq": groq, "gemini": gemini}
        self.counts = {"groq": 0, "gemini": 0}
        self.lock = threading.Lock()
        self.stopped = False
        write_json(path, {"attempted": self.counts, "limits": self.limits})

    def hook(self, provider):
        def before(request):
            expected = "api.groq.com" if provider == "groq" else "generativelanguage.googleapis.com"
            if request.url.host != expected:
                raise RuntimeError("Unexpected provider host")
            with self.lock:
                if self.stopped:
                    raise RuntimeError("Provider failure stopped this live run before send")
                if self.counts[provider] >= self.limits[provider]:
                    raise RuntimeError("Approved provider budget exhausted before send")
                self.counts[provider] += 1
                write_json(self.path, {"attempted": self.counts, "limits": self.limits})
        return before

    def response_hook(self, provider):
        def after(response):
            if response.status_code >= 400:
                with self.lock:
                    self.stopped = True
                    write_json(self.path, {"attempted": self.counts, "limits": self.limits,
                                          "stopped_on": {"provider": provider, "status": response.status_code}})
        return after

    def async_response_hook(self, provider):
        sync_hook = self.response_hook(provider)

        async def after(response):
            sync_hook(response)
        return after

    def async_hook(self, provider):
        sync_hook = self.hook(provider)

        async def before(request):
            sync_hook(request)
        return before


def validate_backend_target(run_dir, app_settings):
    namespace = run_dir.name
    manifest = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    if (not namespace.startswith("f8_02_") or len(namespace) != 38
            or any(c not in "0123456789abcdef" for c in namespace[6:])
            or run_dir.resolve().parent != (ROOT / "frontend/.playwright-tmp").resolve()
            or manifest.get("namespace") != namespace or manifest.get("task") != "F8-02"
            or manifest.get("status") != "IN_PROGRESS"
            or manifest.get("cleanup") != "REQUIRED_OWN_NAMESPACE_ONLY"
            or app_settings.mongodb_db_name != namespace or app_settings.qdrant_collection != namespace
            or Path(app_settings.documents_dir).resolve() != run_dir.resolve() / "raw"):
        raise RuntimeError("Backend refused an unapproved/default namespace")


def serve_backend(run_dir):
    """Real application with real providers; only test transport controls differ."""
    if os.environ.get("F8_02_EXECUTE") != "approved":
        raise RuntimeError("Internal backend mode needs explicit live approval")
    import httpx
    import uvicorn
    from google import genai
    from google.genai.types import HttpOptions, HttpRetryOptions
    from langchain_openai import ChatOpenAI
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    from app.shared.config import settings
    validate_backend_target(run_dir, settings)
    import app.chat.pipeline as pipeline
    import app.chat.query_rewriting as rewriting
    import app.rag.retriever as retriever
    import app.documents.ingestion as ingestion
    from app.main import app

    budget = ProviderBudget(run_dir / "provider-budget.json")
    llm = ChatOpenAI(model=settings.llm_model, api_key=settings.groq_api_key.get_secret_value(),
                     base_url=settings.openai_base_url, max_retries=0, max_tokens=256, timeout=45,
                     http_client=httpx.Client(event_hooks={"request": [budget.hook("groq")], "response": [budget.response_hook("groq")]}),
                     http_async_client=httpx.AsyncClient(event_hooks={"request": [budget.async_hook("groq")], "response": [budget.async_response_hook("groq")]}))
    embeddings = GoogleGenerativeAIEmbeddings(model=settings.embedding_model,
                                              google_api_key=settings.embedding_api_key, vertexai=False)
    embeddings.client.close()
    embeddings.client = genai.Client(api_key=settings.embedding_api_key,
        http_options=HttpOptions(timeout=45000, retry_options=HttpRetryOptions(attempts=1),
            httpx_client=httpx.Client(event_hooks={"request": [budget.hook("gemini")], "response": [budget.response_hook("gemini")]}),
            httpx_async_client=httpx.AsyncClient(event_hooks={"request": [budget.async_hook("gemini")], "response": [budget.async_response_hook("gemini")]})))
    pipeline.get_llm = rewriting.get_llm = lambda: llm
    retriever.get_embeddings = ingestion.get_embeddings = lambda: embeddings
    logging.disable(logging.CRITICAL)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="critical", access_log=False)


def wait_http(url, child, timeout=45):
    import httpx
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError("Owned server exited before readiness")
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise TimeoutError("Owned server readiness")


def cleanup_owned_namespace(cloud, namespace, run_id, run_dir, raw_dir):
    """Cleanup independent targets; a cloud error must not skip local cleanup."""
    if (len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id)
            or namespace != "f8_02_" + run_id or run_dir.name != namespace
            or run_dir.resolve().parent != (ROOT / "frontend/.playwright-tmp").resolve()
            or raw_dir.resolve() != run_dir.resolve() / "raw"):
        raise RuntimeError("Cleanup ownership/path mismatch")
    checks = {}
    try:
        qdrant = cloud.qdrant.client
        if qdrant.collection_exists(namespace):
            qdrant.delete_collection(namespace)
        checks["qdrant_absent"] = not qdrant.collection_exists(namespace)
    except Exception as exc:
        checks["qdrant_error_type"] = type(exc).__name__
    try:
        mongo = cloud.mongodb.client
        try:
            mongo.drop_database(namespace)
        except Exception as exc:
            checks["drop_database_error_type"] = type(exc).__name__
            checks["drop_database_error_code"] = getattr(exc, "code", None)
            # Some Atlas roles restrict dropDatabase but allow dropCollection.
            # All collections are owned: namespace was absent before this run.
            database = mongo[namespace]
            for name in database.list_collection_names():
                database.drop_collection(name)
        checks["mongo_absent"] = namespace not in mongo.list_database_names()
    except Exception as exc:
        checks["mongo_error_type"] = type(exc).__name__
        checks["mongo_error_code"] = getattr(exc, "code", None)
    try:
        for file in sorted(raw_dir.rglob("*"), reverse=True) if raw_dir.exists() else []:
            if file.is_file():
                file.unlink()
            elif file.is_dir():
                file.rmdir()
        if raw_dir.exists():
            raw_dir.rmdir()
        checks["raw_absent"] = not raw_dir.exists()
    except Exception as exc:
        checks["raw_error_type"] = type(exc).__name__
    clean = all(checks.get(name) is True for name in ("qdrant_absent", "mongo_absent", "raw_absent"))
    return {"status": "PASS" if clean else "BLOCKED", "verification": checks}


def run_live(args):
    run_id = uuid4().hex
    namespace = "f8_02_" + run_id
    run_dir = ROOT / "frontend" / ".playwright-tmp" / namespace
    raw_dir = run_dir / "raw"
    plan = {"task": "F8-02", "namespace": namespace, "limits": {"groq": 5, "gemini": 4},
            "status": "PLAN_ONLY", "session_ids": [], "document_ids": [], "checks": {},
            "cleanup": "NO_RESOURCES_CREATED"}
    if not args.execute:
        print(json.dumps(plan))
        return 0
    if not args.approve_temporary_namespace or args.approved_groq != 5 or args.approved_gemini != 4:
        raise RuntimeError("Explicit matching provider and temporary namespace approvals required")
    plan["status"] = "IN_PROGRESS"
    run_dir.mkdir(parents=True, exist_ok=False)
    report_path = run_dir / "report.json"
    write_json(report_path, plan)
    children, logs = [], []
    cloud = None
    owns_namespace = False
    stage = "ports"
    try:
        for port in (8000, 3000):
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
        from app.shared.config import Settings, settings
        from app.infrastructure.connections import CloudConnections
        if namespace in {settings.mongodb_db_name, settings.qdrant_collection}:
            raise RuntimeError("Test namespace must differ from default")
        isolated = Settings(mongodb_db_name=namespace, qdrant_collection=namespace, documents_dir=str(raw_dir))
        cloud = CloudConnections(isolated)
        stage = "cloud_preflight"
        statuses = cloud.connect_all()
        plan["checks"][stage] = {name: {"ok": item.ok, "code": item.code} for name, item in statuses.items()}
        if not all(item.ok for item in statuses.values()):
            raise RuntimeError("Cloud health blocked")
        if namespace in cloud.mongodb.client.list_database_names():
            raise RuntimeError("Refuse an existing Mongo namespace")
        if namespace in [c.name for c in cloud.qdrant.client.get_collections().collections]:
            raise RuntimeError("Refuse an existing Qdrant namespace")
        owns_namespace = True
        plan["cleanup"] = "REQUIRED_OWN_NAMESPACE_ONLY"
        write_json(report_path, plan)
        environment = {**os.environ, "MONGODB_DB_NAME": namespace, "QDRANT_COLLECTION": namespace,
                       "DOCUMENTS_DIR": str(raw_dir), "F8_02_EXECUTE": "approved",
                       "NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:8000"}
        stage = "frontend_build"
        with (run_dir / "build.log").open("w", encoding="utf-8") as build_log:
            result = subprocess.run(["node", "node_modules/next/dist/bin/next", "build"], cwd=ROOT / "frontend",
                                    env=environment, stdout=build_log, stderr=subprocess.STDOUT, timeout=180)
        if result.returncode:
            raise RuntimeError("Live configured production build failed")
        plan["checks"][stage] = "PASS"
        commands = [([sys.executable, str(Path(__file__)), "--backend", str(run_dir)], ROOT),
                    (["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3000"], ROOT / "frontend")]
        for index, (command, cwd) in enumerate(commands):
            log = (run_dir / f"server-{index}.log").open("w", encoding="utf-8")
            logs.append(log)
            children.append(subprocess.Popen(command, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        stage = "http_health"
        wait_http("http://127.0.0.1:8000/health", children[0])
        wait_http("http://127.0.0.1:3000/chat", children[1])
        import httpx
        health = httpx.get("http://127.0.0.1:8000/health/dependencies", timeout=20)
        plan["checks"][stage] = {"status": health.status_code, "ready": health.json().get("status")}
        if health.status_code != 200:
            raise RuntimeError("Readiness not healthy")
        stage = "browser_live"
        browser = subprocess.run(["node", "scripts/controlled-live-browser.mjs", str(run_dir)], cwd=ROOT / "frontend",
                                 env={**environment, "TMP": str(run_dir), "TEMP": str(run_dir)}, timeout=360)
        if (run_dir / "browser.json").exists():
            plan["browser"] = json.loads((run_dir / "browser.json").read_text(encoding="utf-8"))
        if browser.returncode:
            raise RuntimeError("Browser live assertions did not complete")
        plan["status"] = "PASS"
    except Exception as exc:
        plan["status"] = "BLOCKED"
        plan["blocked_stage"] = stage
        plan["error_type"] = type(exc).__name__
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)
        for log in logs:
            log.close()
        if (run_dir / "browser.json").exists():
            plan["browser"] = json.loads((run_dir / "browser.json").read_text(encoding="utf-8"))
            plan["session_ids"] = plan["browser"]["session_ids"]
            plan["document_ids"] = plan["browser"]["document_ids"]
        if (run_dir / "provider-budget.json").exists():
            plan["providers"] = json.loads((run_dir / "provider-budget.json").read_text(encoding="utf-8"))
        if owns_namespace and cloud is not None:
            try:
                cleanup = cleanup_owned_namespace(cloud, namespace, run_id, run_dir, raw_dir)
                plan["cleanup"] = cleanup["status"]
                plan["cleanup_verification"] = cleanup["verification"]
            except Exception as exc:
                plan["cleanup"] = "BLOCKED"
                plan["cleanup_error_type"] = type(exc).__name__
        if cloud is not None:
            cloud.close()
        if plan["cleanup"] not in {"PASS", "NO_RESOURCES_CREATED"}:
            plan["status"] = "BLOCKED"
        write_json(report_path, plan)
        print(json.dumps({"report": str(report_path.relative_to(ROOT)), "status": plan["status"],
                          "blocked_stage": plan.get("blocked_stage"), "cleanup": plan["cleanup"], "providers": plan.get("providers")}))
    return 0 if plan["status"] == "PASS" else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approved-groq", type=int)
    parser.add_argument("--approved-gemini", type=int)
    parser.add_argument("--approve-temporary-namespace", action="store_true")
    parser.add_argument("--backend", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.backend:
        try:
            serve_backend(args.backend)
        except Exception as exc:
            print(json.dumps({"backend_start_error_type": type(exc).__name__}))
            sys.exit(2)
    else:
        sys.exit(run_live(args))
