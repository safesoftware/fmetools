# coding: utf-8

from __future__ import absolute_import, division, print_function, unicode_literals

import logging

import pytest
from fmeobjects import FMEFeature
from logging import LogRecord

from fmetools.logfile import FMELogFormatter, FMELogHandler, FMELoggerAdapter


class DebugLogRecord(LogRecord):
    def __init__(self, msg, args=None, level=logging.INFO, no_prefix=False):
        if args is None:
            args = ()
        self.no_prefix = no_prefix
        super(DebugLogRecord, self).__init__("logname", level, "", 1, msg, args, None)


@pytest.fixture
def formatter():
    return FMELogFormatter()


@pytest.fixture
def handler():
    return FMELogHandler()


@pytest.fixture
def adapter():
    return FMELoggerAdapter(logging.getLogger(), {"foo": "bar"})


def test_log_formatter_msg_string(formatter):
    output = formatter.format(DebugLogRecord("foo bar"))
    assert "logname: foo bar" == output


def test_log_formatter_msg_string_param_substitution(formatter):
    output = formatter.format(DebugLogRecord("foo %s bar %d", ("baz", 0)))
    assert "logname: foo baz bar 0" == output


def test_log_formatter_msg_string_debug_prefix(formatter):
    output = formatter.format(DebugLogRecord("foo", level=logging.DEBUG))
    assert "DEBUG: logname: foo" == output


def test_log_formatter_no_log_prefix(formatter):
    record = DebugLogRecord(0, no_prefix=True)
    assert "0" == formatter.format(record)

    # Message strings never receive prepended params.
    record = DebugLogRecord("foo %s", ("bar",), no_prefix=True)
    assert "foo bar" == formatter.format(record)


def test_log_formatter_cast_msg_params():
    """Test that message parameters are cast correctly, and modify the input list."""
    params = [0, 0.0, True, None, "foo", "车神", "é"]
    assert params == FMELogFormatter.cast_msg_params(params)
    assert params == ["0", "0.0", "True", "None", "foo", "车神", "é"]


def test_log_handler_feature_logging(handler):
    handler.emit(DebugLogRecord(FMEFeature()))


def test_log_handler_instance_equality(handler):
    a, b = handler, FMELogHandler()
    assert a == b


def test_log_adapter_default_prefix_behaviour(adapter):
    msg, kwargs = adapter.process(0, {"biz": "baz"})
    assert 0 == msg
    assert "foo" in kwargs["extra"]
    assert "biz" in kwargs
    assert kwargs["extra"]["no_prefix"] is False


@pytest.mark.parametrize("no_prefix_option", [True, False])
def test_log_adapter_no_prefix_option(adapter, no_prefix_option):
    _, kwargs = adapter.process(0, {"extra": {"no_prefix": no_prefix_option}})
    assert kwargs["extra"]["no_prefix"] == no_prefix_option
