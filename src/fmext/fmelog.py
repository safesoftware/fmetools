"""
Logging system for FME that builds upon the Python standard library's
logging module, but emits messages to FMELogFile under the hood, and adds
functionality.

Internal use only.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from fmeobjects import FMELogFile, FMEFeature, FME_WARN, FME_INFORM, FME_ERROR, FME_FATAL
import fme

import logging
from six import string_types


class FMELogFormatter(logging.Formatter):
    """Formats log records for display.

    For message numbers, the message and parameters are sent to :class:`fmeobjects.FMELogFile`, and the resolved message string is returned.
    For string messages, string substitution is performed, and the result returned.

    For messages at DEBUG level, a 'DEBUG: ' prefix is added.
    """

    def __init__(self):
        super(FMELogFormatter, self).__init__()

    def format(self, record):
        if isinstance(record.msg, int):
            msg_params = list(record.args)
            try:
                if record.prepended_params:
                    msg_params = list(record.prepended_params)
                    msg_params.extend(record.args)
            except AttributeError:
                # LogRecords don't necessarily have prepended_params, as it's something we add.
                pass
            # FMELogFile is local due to FMESession leak issues when participating in Python's singleton logging system.
            msg_string = FMELogFile().getMessage(
                record.msg, FMELogFormatter.cast_msg_params(msg_params)
            )
        else:
            # Only attempt substitutions in string messages if caller provided arguments.
            # Otherwise, '%xx' in message could be misinterpreted as placeholders and cause errors.
            msg_string = record.msg
            if record.args:
                msg_string = record.msg % record.args

        if record.levelno == logging.DEBUG:
            msg_string = "DEBUG: " + msg_string

        return msg_string

    @staticmethod
    def cast_msg_params(params):
        """Cast the message params to type string.

        :param list params: List of parameters.
        :rtype: list(str)
        """
        for i, value in enumerate(params):
            if not isinstance(value, string_types):
                params[i] = str(value)
        return params


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
    """Bridges the world of Python logging with the world of FME logging.

    Maps Python log levels to FME message severities.
    Messages are resolved and forwarded to :class:`fmeobjects.FMELogFile` with the appropriate severity level.

    :class:`fmeobjects.FMEFeature` logging is intercepted here and sent straight to :class:`fmeobjects.FMELogFile`.
    """

    def __init__(self):
        super(FMELogHandler, self).__init__()
        self.formatter = FMELogFormatter()

    def __hash__(self):
        return 0

    def emit(self, record):
        # FMELogFile is local due to FMESession leak issues when participating in Python's singleton logging system.
        fme_severity = LEVEL_NUM_TO_FME[record.levelno]
        if isinstance(record.msg, FMEFeature):
            FMELogFile().logFeature(record.msg, fme_severity, 20)
            return
        # Call superclass method that will end up calling the formatter defined in the constructor.
        msgStr = self.format(record)
        FMELogFile().logMessageString(msgStr, fme_severity)

    # This ensures that only one instance of this class can be in a Logger's list of handlers.
    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def __ne__(self, other):
        return not self.__eq__(other)


class FMELoggerAdapter(logging.LoggerAdapter):
    """Logger with the ability to specify default message parameters to start
    off any message parameter list. For use with :class:`FMELogFormatter`,
    which recognizes the keyword arguments involved.

    Logging methods accept a keyword ``no_prepend_args``. If True, nothing will be prepended to message parameters.

    :ivar prepended_params: Message parameters to prepend to all message parameters.
       Intended for frequent log message prefixes, like format name and direction.
    """

    def __init__(self, logger, extras):
        super(FMELoggerAdapter, self).__init__(logger, extras)
        self.prepended_params = None

    def process(self, msg, kwargs):
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        extra = kwargs["extra"]
        extra.update(self.extra)
        if not extra.get("no_prepend_args", False):
            extra["prepended_params"] = self.prepended_params
        return msg, kwargs

    def warn(self, msg, *args, **kwargs):
        """Alias for :meth:`warning`, to maintain identical API to
        :class:`logging.Logger`."""
        return self.warning(msg, *args, **kwargs)


def get_configured_logger(name="fmelog", debug=None):
    """Get an object that can be used for Python-style logging.

    :param str name: Logger name to obtain.
    :param bool debug: Whether debug-level messages should be logged.
        If None, then this will be set to True if FME_DEBUG is in fme.macroValues.
    :rtype: FMELoggerAdapter
    """
    logger = logging.getLogger(name)
    if debug is None:
        try:
            if fme.macroValues["FME_DEBUG"]:
                debug = True
        except (AttributeError, KeyError):
            debug = False
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    # Don't duplicate messages to the parent (root) logger.
    # The root logger isn't set up to handle FME msgnums,
    # causing an exception message in stderr every time a msgnum is logged in unit tests.
    logger.propagate = False

    # Method checks for duplicates before adding.
    # This is designed to avoid duplicated handlers when, for instance,
    # a plugin is instantiated multiple times during the life of fme.exe.
    # Remember that Python's loggers are singletons.
    handler = FMELogHandler()
    logger.addHandler(handler)

    log_adapter = FMELoggerAdapter(logger, {})
    log_adapter.debug("Configured logging for %s" % name)
    return log_adapter
