"""Offline concurrency investigation; no external network or provider smoke."""
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex


def local_only(address):
    if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("Isolation investigation: external network disabled")


def connect(sock, address):
    local_only(address)
    return original_connect(sock, address)


def connect_ex(sock, address):
    local_only(address)
    return original_connect_ex(sock, address)


socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
suite = unittest.defaultTestLoader.loadTestsFromNames([
    "tests.test_multi_session_isolation", "tests.test_conversation_concurrency",
    "tests.test_history", "tests.test_query_rewriting", "tests.test_retriever",
    "tests.test_streaming_pipeline", "tests.test_chat_stream", "tests.test_chat_persistence",
    "tests.test_session_actions", "tests.test_sessions_api",
])
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
