"""Log files: problems go to errors.log, crash reports never hold full numbers."""
import logging

from app.logging_setup import PiiMaskFilter


def test_crash_report_is_masked():
    try:
        raise ValueError("bad mobile 9876543210")
    except ValueError:
        import sys
        rec = logging.LogRecord("x", logging.ERROR, "f", 1, "failed for %s", ("11111111111",), sys.exc_info())
    PiiMaskFilter().filter(rec)
    text = logging.Formatter().format(rec)
    assert "9876543210" not in text and "11111111111" not in text
    assert "******3210" in text and "Traceback" in text
