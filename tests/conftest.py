"""
tests/conftest.py
Shared fixtures for the test suite.
"""

import sys
from pathlib import Path

import pytest

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture()
def client():
    """Flask test client with the engine reset before every test."""
    from src.app import app, engine

    app.config["TESTING"] = True
    engine._paragraphs = []
    engine._filename = ""
    engine._cache.clear()
    engine._inflight.clear()

    with app.test_client() as c:
        yield c


@pytest.fixture()
def engine():
    """Create a fresh TTSEngine for every test."""
    from src.tts_engine import TTSEngine

    return TTSEngine()
