"""
Generic exceptions with pre-configured messages, for use in FME format
plugins.

These exception classes help ensure that the correct messages are used,
and with the correct message parameters.
"""

from __future__ import absolute_import, division, print_function, unicode_literals
import traceback, inspect

from fmeobjects import FMEException, FMEFeature
from fmegeneral.fmeconstants import kFME_MSGNUM_WRITER_FEATURE_MISSING_COORDSYS, kFME_MSGNUM_WRITER_REPROJECTION_FAILED, \
   kFME_MSGNUM_WRITER_MODE_UNSUPPORTED, kFME_MSGNUM_INTERNAL_ERROR


class MissingDefForIncomingFeatureType(FMEException):
    """For use in writers.

    Raise when the writer receives a feature with a feature type that
    doesn't match any of the writer's DEF lines. This can happen when
    working with dynamic schema.
    """

    msgNum = 926853

    def __init__(self, writerName, feature):
        """
      :param str writerName: The name of the writer.
      :param fmeobjects.FMEFeature feature: The offending feature.
      """
        super(MissingDefForIncomingFeatureType, self).__init__(
            self.msgNum, [writerName, feature.getFeatureType()])


class FeatureMissingCoordinateSystem(FMEException):
    """For use in writers.

    Raise when the writer receives a feature that has no coordinate
    system, but the writer requires one.
    """

    msgNum = kFME_MSGNUM_WRITER_FEATURE_MISSING_COORDSYS

    def __init__(self, writerName):
        """
      :param str writerName: The name of the writer.
      :param fmeobjects.FMEFeature feature: The offending feature.
      """
        super(FeatureMissingCoordinateSystem, self).__init__(
            self.msgNum, [writerName])


class FeatureReprojectionFailed(FMEException):
    """For use in writers.

    Raise when reprojection of the coordinate system failed.
    """

    msgNum = kFME_MSGNUM_WRITER_REPROJECTION_FAILED

    def __init__(self, writerName, sourceCoordSys, destCoordSys):
        """
      :param str writerName: The name of the writer.
      :param fmeobjects.FMEFeature feature: The offending feature.
      """
        super(FeatureReprojectionFailed, self).__init__(
            self.msgNum, [writerName, sourceCoordSys, destCoordSys])


class WriterModeUnsupported(FMEException):
    """For use in writers.

    Raise when a ``fme_db_operation`` or ``fme_feature_operation`` value is
    unsupported.
    """

    msgNum = kFME_MSGNUM_WRITER_MODE_UNSUPPORTED

    def __init__(self, writerName, unsupportedMode):
        """
      :param str writerName: The name of the writer.
      :param str unsupportedMode: The offending mode encountered.
      :param fmeobjects.FMEFeature feature: The offending feature.
      """
        super(WriterModeUnsupported,
              self).__init__(self.msgNum, [writerName, unsupportedMode])


class InternalErrorException(FMEException):
    """Exception raised when a helper function receives an invalid or
    unexpected value not caused by user input. Something is deeply wrong if
    this exception is raised.

    If using this as a wrapper for an existing exception, you should be able to just unpack ``sys.exc_info()`` into the
    constructor, resulting in a call that looks like ``InternalErrorException(writer_name, *sys.exc_info())``. If
    raising as its own error, make sure to declare the type as None.
    """

    msgNum = kFME_MSGNUM_INTERNAL_ERROR

    def __init__(self, component_name, err_type, err_msg, tb):
        """
        :type component_name: six.text_type
        :type err_type: None or class
        :type err_msg: six.text_type
        :type tb: types.TracebackType or list
        :param component_name: The name of the component (eg, writer) raising the exception.
        :param err_type: The error type. (``sys.exc_info()[0]`` if wrapping an exception, None if
           originating an error.)
        :param err_msg: The content of the error message. (``sys.exc_info()[1]`` if wrapping an exception.)
        :param tb: Trace information. Either a traceback object (``sys.exc_info()[2]``) or an
            iterable of filename, line. The static method make_trace() can be used to create an appropriate trace.
        """
        if err_type:
            trace_string = ""
            for trace in traceback.extract_tb(tb):
                trace_string += "File: {}, line: {}, function: {}, text: {}\n".format(
                    *trace)
            # In 2.7, assigning the traceback to a name can create a circular reference that isn't garbage collected, so we
            # explicitly delete it as a precaution.
            del tb
            msg_string = "{}: {}\n Trace: {}".format(err_type.__name__,
                                                     err_msg, trace_string)
        else:
            msg_string = "Error in {} at line {}: {}".format(
                tb[0], tb[1], err_msg)
        super(InternalErrorException,
              self).__init__(self.msgNum, [component_name, msg_string])

    @staticmethod
    def make_trace(filename):
        return [filename, inspect.currentframe().f_back.f_lineno]
