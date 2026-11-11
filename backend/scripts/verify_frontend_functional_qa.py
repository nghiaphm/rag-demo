"""F7-03-05 offline gate. Includes the terminal parity regression (may FAIL).

Loopback socket pairs are needed by Windows asyncio/TestClient. External TCP
connections are rejected before importing application/test modules.
"""
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex


def local_only(address):
    if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("Functional QA forbids external TCP connections")


def connect(sock, address):
    local_only(address)
    return original_connect(sock, address)


def connect_ex(sock, address):
    local_only(address)
    return original_connect_ex(sock, address)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
names = [
    "tests.integration.test_sessions_api", "tests.unit.test_session_actions",
    "tests.unit.test_conversation_models", "tests.unit.test_conversation_concurrency",
    "tests.integration.test_documents_api", "tests.integration.test_ingestion", "tests.integration.test_chat_stream",
    "tests.integration.test_chat_persistence", "tests.unit.test_sse_schema", "tests.integration.test_cors",
    "tests.integration.test_stream_terminal_parity",
]
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
