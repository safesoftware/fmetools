# coding: utf-8

from __future__ import absolute_import, division, print_function, unicode_literals

import logging

try:
    from unittest.mock import patch, MagicMock
except ImportError:
    from mock import patch, MagicMock  # PY2 backport library


import fmeobjects
from fmeobjects import FMEFeature

from hypothesis import given, settings
from hypothesis.strategies import sampled_from, booleans

from fmetools.logfile import (
    FMELogHandler,
    get_configured_logger,
    LEVEL_NUM_TO_FME,
)


def test_log_handler_instance_equality():
    assert FMELogHandler() == FMELogHandler()


def test_logger_debug_autoconfig(monkeypatch):
    """
    Verify logger's default log level based on FME_DEBUG key presence in fme.macroValues,
    or macroValues being undefined (for older FME).
    """
    with patch("fmetools.logfile.fme.macroValues", new={}, create=True) as macrovalues:
        assert get_configured_logger().getEffectiveLevel() == logging.INFO
        macrovalues["FME_DEBUG"] = "foobar"
        assert get_configured_logger().getEffectiveLevel() == logging.DEBUG
    monkeypatch.delattr("fmetools.logfile.fme.macroValues", raising=False)
    assert get_configured_logger().getEffectiveLevel() == logging.INFO


@given(py_severity=sampled_from(sorted(LEVEL_NUM_TO_FME.keys())), debug_mode=booleans())
def test_log_output(py_severity, debug_mode):
    """
    - Filtering of debug messages based on whether the logger is in debug mode.
    - Python log severity maps correctly to FME log severity.
    - Prefixing of all messages.
    - Prefixing of debug messages.
    """
    mock_logfile = MagicMock(fmeobjects.FMELogFile)
    with patch("fmetools.logfile.FMELogFile", return_value=mock_logfile):
        logger = get_configured_logger(name="test", debug=debug_mode)
        logger.log(py_severity, "hello %s", "world")
        expected_msg = "test: hello world"
        if debug_mode:
            if py_severity < logging.DEBUG:
                # Msgs less than debug level are ignored,
                # so the last logged msg is only the one about enabling debug logging.
                mock_logfile.logMessageString.assert_called_with(
                    "DEBUG: test: Debug logging enabled",
                    LEVEL_NUM_TO_FME[logging.DEBUG],
                )
            else:
                if py_severity == logging.DEBUG:
                    expected_msg = "DEBUG: " + expected_msg
                mock_logfile.logMessageString.assert_called_with(
                    expected_msg, LEVEL_NUM_TO_FME[py_severity]
                )
        else:
            if py_severity <= logging.DEBUG:
                assert not mock_logfile.logMessageString.called
            else:
                mock_logfile.logMessageString.assert_called_with(
                    expected_msg, LEVEL_NUM_TO_FME[py_severity]
                )


@given(py_severity=sampled_from(sorted(LEVEL_NUM_TO_FME.keys())), debug_mode=booleans())
@settings(deadline=None)
def test_log_feature(py_severity, debug_mode):
    """
    Logger passes FMEFeature to the right method, using the right severity.
    """
    mock_logfile = MagicMock(fmeobjects.FMELogFile)
    with patch("fmetools.logfile.FMELogFile", return_value=mock_logfile):
        logger = get_configured_logger(debug=debug_mode)
        feature = FMEFeature()
        logger.log(py_severity, feature)

        if py_severity < logging.DEBUG:
            assert not mock_logfile.logFeature.called
        elif py_severity == logging.DEBUG and not debug_mode:
            assert not mock_logfile.logFeature.called
        else:
            mock_logfile.logFeature.assert_called_with(
                feature, LEVEL_NUM_TO_FME[py_severity]
            )
