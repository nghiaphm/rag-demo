"""Static architecture tests enforcing one-way dependency rules across backend/app packages.

Uses Python AST to inspect all module-level imports and verify strict adherence
to the target architecture dependency rules:

1. api            -> chat, conversations, documents, shared
2. chat           -> rag, conversations, tool_use, shared
3. documents      -> rag, tool_use, shared (infrastructure ONLY via ports.py / vector_index)
4. rag            -> shared (NO concrete infrastructure, NO chat/api)
5. tool_use       -> shared (NO documents, chat, api)
6. infrastructure -> shared, implements ports (NO api, chat)
7. shared         -> self-contained (NO internal feature imports)
8. SSE isolation  -> ONLY api.streaming may import sse_schema; chat and rag MUST NOT.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

APP_DIR = Path(__file__).resolve().parents[2] / "app"


def _get_module_level_imports(file_path: Path) -> list[str]:
    """Extract all module-level import targets from a Python file."""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as exc:
        raise RuntimeError(f"Cannot parse {file_path}: {exc}") from exc

    targets: list[str] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                targets.append(alias.name)
        elif isinstance(stmt, ast.ImportFrom):
            if stmt.module:
                targets.append(stmt.module)
    return targets


def _get_package_imports(pkg_name: str) -> dict[str, list[str]]:
    """Return a mapping of file_name -> list of internal app.* module imports."""
    pkg_dir = APP_DIR / pkg_name
    result: dict[str, list[str]] = {}
    if not pkg_dir.exists():
        return result

    for py_file in pkg_dir.rglob("*.py"):
        rel_path = py_file.relative_to(APP_DIR).as_posix()
        imports = _get_module_level_imports(py_file)
        app_imports = [imp for imp in imports if imp.startswith("app.") or imp == "app"]
        if app_imports:
            result[rel_path] = app_imports
    return result


class ArchitectureDependencyTests(unittest.TestCase):
    """Verify one-way package dependency directions via AST inspection."""

    def test_shared_imports_no_internal_modules(self) -> None:
        """Rule: shared -> khong import module nao khac trong app."""
        shared_imports = _get_package_imports("shared")
        violations = []
        for file_path, imports in shared_imports.items():
            for imp in imports:
                if imp != "app.shared" and not imp.startswith("app.shared."):
                    violations.append(f"{file_path} imports {imp}")
        self.assertEqual(violations, [], f"shared has illegal internal dependencies: {violations}")

    def test_tool_use_imports_only_shared_and_itself(self) -> None:
        """Rule: tool_use -> shared (KHONG import documents, chat, api, rag, infrastructure)."""
        tool_imports = _get_package_imports("tool_use")
        violations = []
        allowed = ("app.shared", "app.tool_use")
        for file_path, imports in tool_imports.items():
            for imp in imports:
                if not any(imp == a or imp.startswith(f"{a}.") for a in allowed):
                    violations.append(f"{file_path} imports {imp}")
        self.assertEqual(violations, [], f"tool_use has illegal dependencies: {violations}")

    def test_infrastructure_implements_ports_and_never_imports_api_or_chat(self) -> None:
        """Rule: infrastructure implement port, KHONG import api hoac chat."""
        infra_imports = _get_package_imports("infrastructure")
        violations = []
        forbidden_prefixes = ("app.api", "app.chat")
        for file_path, imports in infra_imports.items():
            for imp in imports:
                if any(imp == fb or imp.startswith(f"{fb}.") for fb in forbidden_prefixes):
                    violations.append(f"{file_path} imports {imp}")
        self.assertEqual(violations, [], f"infrastructure imports api/chat: {violations}")

    def test_rag_does_not_import_infrastructure_chat_or_api(self) -> None:
        """Rule: rag -> shared (KHONG import infrastructure cu the, KHONG import chat/api)."""
        rag_imports = _get_package_imports("rag")
        violations = []
        forbidden_prefixes = ("app.infrastructure", "app.chat", "app.api")
        for file_path, imports in rag_imports.items():
            for imp in imports:
                if any(imp == fb or imp.startswith(f"{fb}.") for fb in forbidden_prefixes):
                    violations.append(f"{file_path} imports forbidden: {imp}")
        self.assertEqual(violations, [], f"rag has forbidden dependencies: {violations}")

    def test_documents_does_not_statically_import_infrastructure(self) -> None:
        """Rule: documents -> rag, tool_use, shared (dung infrastructure CHI qua ports.py)."""
        doc_imports = _get_package_imports("documents")
        violations = []
        for file_path, imports in doc_imports.items():
            for imp in imports:
                if imp == "app.infrastructure" or imp.startswith("app.infrastructure."):
                    violations.append(f"{file_path} imports concrete infrastructure: {imp}")
                if imp == "app.chat" or imp.startswith("app.chat."):
                    violations.append(f"{file_path} imports chat: {imp}")
                if imp == "app.api" or imp.startswith("app.api."):
                    violations.append(f"{file_path} imports api: {imp}")
        self.assertEqual(violations, [], f"documents has illegal dependencies: {violations}")

    def test_conversations_does_not_import_chat_or_api_or_infrastructure(self) -> None:
        """Rule: conversations -> models, documents.models, shared (one-way: chat -> conversations)."""
        conv_imports = _get_package_imports("conversations")
        violations = []
        forbidden_prefixes = ("app.chat", "app.api", "app.infrastructure")
        for file_path, imports in conv_imports.items():
            for imp in imports:
                if any(imp == fb or imp.startswith(f"{fb}.") for fb in forbidden_prefixes):
                    violations.append(f"{file_path} imports forbidden: {imp}")
        self.assertEqual(violations, [], f"conversations has forbidden dependencies: {violations}")

    def test_chat_does_not_import_api_or_infrastructure(self) -> None:
        """Rule: chat -> rag, conversations, tool_use, shared (KHONG import api, infrastructure)."""
        chat_imports = _get_package_imports("chat")
        violations = []
        forbidden_prefixes = ("app.api", "app.infrastructure")
        for file_path, imports in chat_imports.items():
            for imp in imports:
                if any(imp == fb or imp.startswith(f"{fb}.") for fb in forbidden_prefixes):
                    violations.append(f"{file_path} imports forbidden: {imp}")
        self.assertEqual(violations, [], f"chat has forbidden dependencies: {violations}")

    def test_sse_schema_isolated_to_api_streaming(self) -> None:
        """Rule: Chi api/streaming/ duoc biet SSE. chat/ va rag/ KHONG import sse_schema."""
        for pkg_name in ("chat", "rag", "conversations", "documents", "tool_use", "infrastructure", "shared"):
            pkg_dir = APP_DIR / pkg_name
            if not pkg_dir.exists():
                continue
            for py_file in pkg_dir.rglob("*.py"):
                imports = _get_module_level_imports(py_file)
                for imp in imports:
                    if "sse_schema" in imp:
                        self.fail(f"Illegal sse_schema import found in {py_file}: {imp}")

    def test_api_does_not_import_infrastructure(self) -> None:
        """Rule: api -> chat, conversations, documents, shared (KHONG import infrastructure)."""
        api_imports = _get_package_imports("api")
        violations = []
        for file_path, imports in api_imports.items():
            for imp in imports:
                if imp == "app.infrastructure" or imp.startswith("app.infrastructure."):
                    violations.append(f"{file_path} imports infrastructure: {imp}")
        self.assertEqual(violations, [], f"api imports infrastructure: {violations}")


if __name__ == "__main__":
    unittest.main()
