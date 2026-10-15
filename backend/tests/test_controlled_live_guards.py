"""Offline safety regressions; no provider/cloud imports or HTTP requests."""
import asyncio
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("f8_live_runner", ROOT / "backend/scripts/controlled_live_e2e.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ControlledLiveGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = ROOT / "frontend/.playwright-tmp"
        temporary.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.directory.cleanup)
        self.budget = runner.ProviderBudget(Path(self.directory.name) / "budget.json", groq=2, gemini=1)

    def request(self, host):
        return SimpleNamespace(url=SimpleNamespace(host=host))

    def test_cap_is_enforced_before_extra_http_attempt(self):
        hook = self.budget.hook("groq")
        for _ in range(2):
            hook(self.request("api.groq.com"))
        with self.assertRaises(RuntimeError):
            hook(self.request("api.groq.com"))
        self.assertEqual(self.budget.counts["groq"], 2)
        self.assertEqual(self.budget.counts["gemini"], 0)

    def test_unexpected_host_never_consumes_budget(self):
        with self.assertRaises(RuntimeError):
            self.budget.hook("groq")(self.request("unexpected.invalid"))
        self.assertEqual(self.budget.counts["groq"], 0)

    def test_async_embedding_hook_enforces_its_own_cap(self):
        async def run():
            hook = self.budget.async_hook("gemini")
            await hook(self.request("generativelanguage.googleapis.com"))
            with self.assertRaises(RuntimeError):
                await hook(self.request("generativelanguage.googleapis.com"))
        asyncio.run(run())
        self.assertEqual(self.budget.counts["gemini"], 1)

    def test_provider_error_opens_circuit_without_retrying_another_provider(self):
        self.budget.hook("groq")(self.request("api.groq.com"))
        self.budget.response_hook("groq")(SimpleNamespace(status_code=429))
        with self.assertRaises(RuntimeError):
            self.budget.hook("gemini")(self.request("generativelanguage.googleapis.com"))
        self.assertEqual(self.budget.counts, {"groq": 1, "gemini": 0})

    def test_plan_only_default_and_missing_approvals_are_fail_closed(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(runner.run_live(SimpleNamespace(execute=False)), 0)
        self.assertEqual(json.loads(output.getvalue())["cleanup"], "NO_RESOURCES_CREATED")
        with self.assertRaises(RuntimeError):
            runner.run_live(SimpleNamespace(execute=True, approve_temporary_namespace=False))

    def cleanup_case(self, fail_collection=False):
        nonce = runner.uuid4().hex
        namespace = "f8_02_" + nonce
        run_dir = ROOT / "frontend/.playwright-tmp" / namespace
        raw_dir = run_dir / "raw"
        raw_dir.mkdir(parents=True)
        (raw_dir / "synthetic.txt").write_text("synthetic")
        self.addCleanup(run_dir.rmdir)
        class DropDatabaseUnavailable(Exception):
            code = 8000

        class Mongo:
            names = ["documents", "sessions"]

            def drop_database(self, name):
                assert name == namespace
                raise DropDatabaseUnavailable()

            def __getitem__(self, name):
                assert name == namespace
                return self

            def list_collection_names(self):
                return list(self.names)

            def drop_collection(self, name):
                if fail_collection:
                    raise RuntimeError("synthetic cleanup failure")
                self.names.remove(name)

            def list_database_names(self):
                return [namespace] if self.names else []

        class Qdrant:
            present = True

            def collection_exists(self, name):
                assert name == namespace
                return self.present

            def delete_collection(self, name):
                assert name == namespace
                self.present = False

        cloud = SimpleNamespace(mongodb=SimpleNamespace(client=Mongo()), qdrant=SimpleNamespace(client=Qdrant()))
        return cloud, namespace, nonce, run_dir, raw_dir

    def test_atlas_drop_database_failure_falls_back_to_owned_collections(self):
        cloud, namespace, nonce, run_dir, raw_dir = self.cleanup_case()
        result = runner.cleanup_owned_namespace(cloud, namespace, nonce, run_dir, raw_dir)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["verification"]["drop_database_error_code"], 8000)
        self.assertFalse(raw_dir.exists())

    def test_cloud_cleanup_failure_does_not_skip_raw_cleanup(self):
        cloud, namespace, nonce, run_dir, raw_dir = self.cleanup_case(fail_collection=True)
        result = runner.cleanup_owned_namespace(cloud, namespace, nonce, run_dir, raw_dir)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(result["verification"]["raw_absent"])
        self.assertTrue(result["verification"]["qdrant_absent"])

    def test_cleanup_ownership_mismatch_refuses_all_deletion(self):
        cloud, namespace, nonce, run_dir, raw_dir = self.cleanup_case()
        with self.assertRaises(RuntimeError):
            runner.cleanup_owned_namespace(cloud, namespace + "_wrong", nonce, run_dir, raw_dir)
        self.assertTrue((raw_dir / "synthetic.txt").exists())
        self.assertTrue(cloud.qdrant.client.present)
        (raw_dir / "synthetic.txt").unlink()
        raw_dir.rmdir()

    def test_internal_backend_refuses_default_or_already_cleaned_namespace(self):
        cloud, namespace, nonce, run_dir, raw_dir = self.cleanup_case()
        manifest_path = run_dir / "report.json"
        self.addCleanup(manifest_path.unlink)
        manifest = {"task": "F8-02", "namespace": namespace, "status": "IN_PROGRESS", "cleanup": "REQUIRED_OWN_NAMESPACE_ONLY"}
        runner.write_json(manifest_path, manifest)
        configured = SimpleNamespace(mongodb_db_name=namespace, qdrant_collection=namespace, documents_dir=str(raw_dir))
        runner.validate_backend_target(run_dir, configured)
        configured.mongodb_db_name = "default_database"
        with self.assertRaises(RuntimeError):
            runner.validate_backend_target(run_dir, configured)
        configured.mongodb_db_name = namespace
        manifest["cleanup"] = "PASS"
        runner.write_json(manifest_path, manifest)
        with self.assertRaises(RuntimeError):
            runner.validate_backend_target(run_dir, configured)
        runner.cleanup_owned_namespace(cloud, namespace, nonce, run_dir, raw_dir)
