"""Backend test suite root — activates deterministic offline config isolation."""

from pathlib import Path
import sys

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from tests._test_env import install_test_environment

install_test_environment()
