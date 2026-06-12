import logging

from logging_setup import setup_logging


def test_default_level_is_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    setup_logging()
    assert logging.getLogger().level == logging.INFO


def test_level_from_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    setup_logging()
    assert logging.getLogger().level == logging.DEBUG


def test_invalid_level_raises(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    try:
        setup_logging()
        raise AssertionError("expected ValueError for invalid LOG_LEVEL")
    except ValueError:
        pass
