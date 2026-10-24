"""Tests never call outside services: the local OCR is used whatever .env says."""
import pytest

from app import config


@pytest.fixture(autouse=True)
def local_ocr(monkeypatch):
    monkeypatch.setattr(config, "OCR_ENGINE", "local")
