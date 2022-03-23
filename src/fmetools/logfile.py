# coding: utf-8

"""
This module bridges FME's :class:`fmeobjects.FMELogFile`
with the :mod:`logging` module in the Python standard library.

Developers should not need to directly use anything in this module,
as the base classes in :mod:`plugins` include preconfigured loggers.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from fmeobjects import (
    FMELogFile,
    FMEFeature,
    FME_WARN,
    FME_INFORM,
    FME_ERROR,
    FME_FATAL,
)
import fme

from . import tr
import logging


class FMELogFormatter(logging.Formatter):
    """
    Formats log records for display in the FME log.
    """

    def format(self, record):
        debug_prefix = "DEBUG: " if record.levelno == logging.DEBUG else ""
        return "{}{}: {}".format(debug_prefix, record.name, record.getMessage())


LEVEL_NUM_TO_FME = {
    logging.NOTSET: FME_WARN,
    logging.DEBUG: FME_WARN,
    logging.INFO: FME_INFORM,
    logging.WARN: FME_WARN,
    logging.ERROR: FME_ERROR,
    logging.CRITICAL: FME_FATAL,
}
FME_TO_LEVEL_NUM = {
    FME_WARN: logging.WARN,
    FME_INFORM: logging.INFO,
    FME_ERROR: logging.ERROR,
    FME_FATAL: logging.CRITICAL,
}


class FMELogHandler(logging.Handler):
    """
    Logs messages to the FME log. Supports logging of :class:`fmeobjects.FMEFeature`.
    """

    def __init__(self):
        super(FMELogHandler, self).__init__()
        self.formatter = FMELogFormatter()

    def __hash__(self):
        return hash(self.__class__.__name__)

    def emit(self, record):
        # FMELogFile is local due to FMESession leak when used in Python's singleton logging system.
        fme_severity = LEVEL_NUM_TO_FME[record.levelno]
        if isinstance(record.msg, FMEFeature):
            FMELogFile().logFeature(record.msg, fme_severity)
            return
        FMELogFile().logMessageString(self.format(record), fme_severity)

    # Ensure that only one instance of this class can be in a Logger's list of handlers.
    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def __ne__(self, other):
        return not self.__eq__(other)


def get_configured_logger(name="fmelog", debug=None):
    """
    Get a logger that outputs messages to the FME log.

    :param str name: Logger name to obtain.
    :param bool debug: Whether debug-level messages should be logged.
        If None, then the setting is inherited from FME.
    :rtype: logging.LoggerAdapter
    """
    logger = logging.getLogger(name)
    if debug is None:
        try:
            if fme.macroValues.get("FME_DEBUG"):
                debug = True
        except AttributeError:
            # On older FME, macroValues only exists when running in FME process
            debug = False
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Method checks for duplicates before adding.
    # This is designed to avoid duplicated handlers when, for instance,
    # a plugin is instantiated multiple times during the life of fme.exe.
    # Python's loggers are singletons.
    handler = FMELogHandler()
    logger.addHandler(handler)

    log_adapter = logging.LoggerAdapter(logger, {})

    log_adapter.debug(tr("Debug logging enabled"))
    return log_adapter
