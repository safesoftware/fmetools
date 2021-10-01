"""
FME PluginBuilder subclasses that provide improved functionality.

Internal use only.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import fme
from fmeobjects import FMEFeature, FMESession
from pluginbuilder import FMEReader, FMEWriter

import six
from fmegeneral import fmeconstants, fmeutil
from fmegeneral.fmeconstants import kFME_REJECTION_CODE, kFME_REJECTION_MESSAGE
from fmegeneral.fmelog import get_configured_logger
from fmegeneral.fmeutil import systemToUnicode
from fmegeneral.parsers import SearchEnvelope, OpenParameters


class FMESimplifiedReader(FMEReader):
    """Base class for Python-based FME reader implementations.

    :param str _typeName: The name used in the following contexts:

          * the name of the format's .db file in the formats info folder
          * the format short name for the format within the .db file
          * ``FORMAT_NAME`` in the metafile

    :param str _keyword: A unique identifier for this reader instance.
    :param FMEMappingFileWrapper _mappingFileWrapper: The :class:`FMEMappingFileWrapper`.
    :param bool _debug: Toggle for debug mode.
    :param Logger _logger: Helper class for logging functionality.
    :param bool _usingConstraints: True if :meth:`setConstraints` was called.
    :param bool _aborted: True if :meth:`abort` was called.
    :param SearchEnvelope _searchEnvelope: An abstraction of the 2D search envelope given by FME
       that's easier to understand.
    :type _featureTypes: list[six.text_type]
    :param _featureTypes: Ordered list of feature types, in Unicode.
    :param _readSchema_generator: Use this member to store any generator used for :meth:`readSchema`.
       Doing so means it'll be be explicitly closed for you in :meth:`close`.
    :param _read_generator: Use this member to store any generator used for :meth:`read`.
       Doing so means it'll be be explicitly closed for you in :meth:`close`.
       :meth:`setConstraints` will both close it and set it to `None`.
       This means :meth:`read` can just check this member for `None` to determine whether it needs to re-instantiate
       its generator to honour new settings.
    """

    def __init__(self, readerTypeName, readerKeyword, mappingFile):
        # super() is intentionally not called.
        # The base class implementation would throw an exception because it doesn't want to be called.
        self._typeName = readerTypeName
        self._keyword = readerKeyword
        self._mappingFileWrapper = FMEMappingFileWrapper(mappingFile, readerKeyword, readerTypeName)

        # Check if the debug flag is set
        self._debug = (
            self._mappingFileWrapper.mappingFile.fetch(fmeconstants.kFME_DEBUG) is not None
        )

        # Instantiate a logger with the appropriate debug mode.
        self._logger = fmeutil.Logger(self._debug)
        self._log = get_configured_logger(self.__class__.__name__, self._debug)

        self._usingConstraints = False
        self._aborted = False
        self._searchEnvelope = None
        self._featureTypes = []

        self._readSchema_generator, self._read_generator = None, None

    def open(self, datasetName, parameters):
        """Open the dataset for reading.

        Does these things for you:

        * Parses the open() parameters.
        * Checks for the debug flag in open() parameters.
        * Calls :meth:`enhancedOpen`.

        If setConstraints() wasn't called earlier, then this method also:
        * Sets `_searchEnvelope` using the mapping file.
        * Sets `_featureTypes` using the mapping file and/or open parameters.

        :param str datasetName: Name of the dataset.
        :param list[str] parameters: List of parameters.
        """

        # If not using setConstraints(), then grab some basic stuff from the mapping file...
        if not self._usingConstraints:
            self._searchEnvelope = self._mappingFileWrapper.getSearchEnvelope()
            self._featureTypes = self._mappingFileWrapper.getFeatureTypes(parameters)

        # Look for the debug flag in the open() parameters.
        openParameters = OpenParameters(datasetName, parameters)
        if openParameters.get(fmeconstants.kFME_DEBUG):
            self._debug = True
            self._logger.setDebugMode(self._debug)
            self._log = get_configured_logger(self.__class__.__name__, self._debug)

        return self.enhancedOpen(openParameters)

    def enhancedOpen(self, openParameters):
        """Implementations shall override this method instead of :meth:`open`.

        :param OpenParameters openParameters: Parameters for the reader.
        """
        pass

    def setConstraints(self, feature):
        """Reset any existing feature generator that represents the state for :meth:`read`.

        :param fmeobjects.FMEFeature feature: An FME feature.
        """
        assert isinstance(feature, FMEFeature)
        self._usingConstraints = True

        # Reset any existing feature generator that represents the state for read().
        if self._read_generator is not None:
            self._read_generator.close()
            self._read_generator = None

    def readSchemaGenerator(self):
        """Generator form of :meth:`readSchema`.

        Simplifies some logic in unit tests by eliminating the need to
        check whether the return value is `None`.
        """
        while True:
            feature = self.readSchema()
            if feature:
                yield feature
            else:
                break

    def readGenerator(self):
        """Generator form of :meth:`read`.

        Simplifies some logic in unit tests by eliminating the need to
        check whether the return value is `None`.
        """
        while True:
            feature = self.read()
            if feature:
                yield feature
            else:
                break

    def abort(self):
        self._aborted = True

    def close(self):
        """This default implementation closes any existing read generators."""
        # In the case that our reader is closed by the infrastructure prior to generators
        # being exhausted of features (e.g. Features to Read cuts things short),
        # it's necessary to close generators explicitly to avoid leaking a session and causing:
        # "Warning: not all FMESessions that were created were destroyed before shutdown. This may cause instability"
        if self._readSchema_generator:
            self._readSchema_generator.close()
        if self._read_generator:
            self._read_generator.close()


class FMESimplifiedWriter(FMEWriter):
    """Base class for Python-based FME writer implementations.

    :param str _typeName: The name used in the following contexts:

          * the name of the format's .db file in the formats info folder
          * the format short name for the format within the .db file
          * ``FORMAT_NAME`` in the metafile

    :param str _keyword: A unique identifier for this writer instance.
    :param FMEMappingFileWrapper _mappingFileWrapper: A wrapper for accessing information from the
       mapping file in a simplified way.
    :param bool _debug: Toggle for debug mode.
    :param Logger _logger: Helper class for logging functionality.
    :param bool _aborted: True if :meth:`abort` was called.
    :type _featureTypes:  list[six.text_type]
    :param _featureTypes: Ordered list of feature types, in Unicode.
    """

    def __init__(self, writerTypeName, writerKeyword, mappingFile):
        # super() is intentionally not called.
        # The base class implementation would throw an exception because it doesn't want to be called.
        self._typeName = writerTypeName
        self._keyword = writerKeyword
        self._mappingFileWrapper = FMEMappingFileWrapper(mappingFile, writerKeyword, writerTypeName)

        # Check if the debug flag is set
        self._debug = (
            self._mappingFileWrapper.mappingFile.fetch(fmeconstants.kFME_DEBUG) is not None
        )

        # Instantiate a logger with the appropriate debug mode.
        self._logger = fmeutil.Logger(self._debug)
        self._log = get_configured_logger(self.__class__.__name__, self._debug)

        self._aborted = False
        self._searchEnvelope = None
        self._featureTypes = []

    def open(self, datasetName, parameters):
        """Open the dataset for writing.

        Does these things for you:

        * Sets `_searchEnvelope` using the mapping file.
        * Sets `_featureTypes` using the mapping file and/or open parameters.
        * Parses the open() parameters.
        * Checks for the debug flag in open() parameters, switching `_logger` to debug mode if present.
        * Calls :meth:`enhancedOpen`.

        :param str datasetName: Name of the dataset.
        :param list[str] parameters: List of parameters.
        """

        self._featureTypes = self._mappingFileWrapper.getFeatureTypes(parameters)

        # Look for the debug flag in the open() parameters.
        openParameters = OpenParameters(datasetName, parameters)
        if openParameters.get(fmeconstants.kFME_DEBUG):
            self._debug = True
            self._logger.setDebugMode(self._debug)
            self._log = get_configured_logger(self.__class__.__name__, self._debug)

        return self.enhancedOpen(openParameters)

    def enhancedOpen(self, openParameters):
        """Implementations shall override this method instead of :meth:`open`.

        :param OpenParameters openParameters: Parameters for the writer.
        """
        pass

    def abort(self):
        self._aborted = True

    def close(self):
        """This default implementation does nothing.

        It's defined here because :class:`pluginbuilder.FMEWriter` requires it to be
        overridden.
        """
        pass


class FMEMappingFileWrapper(object):
    """A wrapper for accessing information from the mapping file in a
    simplified way.

    All methods are like the 'withPrefix' methods on :class:`pluginbuilder.FMEMappingFile`: the plugin keyword and type are assumed
    to be the ones supplied in the constructor. If this assumption doesn't apply, then use the `mappingFile` member.

    The functionality of this wrapper, combined with prefixing of directives in the metafile's `SOURCE_READER` with
    ``-_``, should eliminate the need to look in both open() parameters and the mapping file for the same directive:
    instead, the mapping file can be used exclusively.

    :param pluginbuilder.FMEMappingFile mappingFile: The original mapping file object.
    """

    def __init__(self, mappingFile, pluginKeyword, pluginType):
        """
        :param pluginbuilder.FMEMappingFile mappingFile: The original mapping file object.
        :param str pluginKeyword: Plugin keyword string.
        :param str pluginType: Plugin type string.
        """
        self.mappingFile = mappingFile
        self._pluginKeyword = pluginKeyword
        self._pluginType = pluginType

        self.__session = FMESession()

    def defLines(self):
        """Get an iterable over DEF lines for this plugin.

        :return: iterator
        """
        defFilter = self._pluginKeyword + fmeconstants.kFME_DEFLINE_SUFFIX
        self.mappingFile.startIteration()
        defLineBuffer = self.mappingFile.nextLineWithFilter(defFilter)
        while defLineBuffer is not None:
            yield defLineBuffer
            defLineBuffer = self.mappingFile.nextLineWithFilter(defFilter)

    def fetchWithPrefix(self, pluginType, pluginKeyword, directive):
        """Like :meth:`pluginbuilder.FMEMappingFile.fetchWithPrefix`, except handles the
        Python-specific situation where directive values are returned as
        2-element lists with identical values.

        :param str pluginType: Plugin type string.
        :param str pluginKeyword: Plugin keyword string.
        :param str directive: Name of the directive.
        :return: If the value is scalar or a 2-element list with identical elements, return the element.
           Otherwise, the list is returned as-is.
        :rtype: str
        """
        value = self.mappingFile.fetchWithPrefix(pluginType, pluginKeyword, directive)
        if isinstance(value, list) and len(value) == 2 and value[0] == value[1]:
            # FIXME: This hack hides the issue in the Python mapping file where the same directive is present twice,
            # and so a list with 2 identical values is returned.
            return value[0]
        return value

    def get(self, directive, default=None, decodeWWJD=True, asList=False):
        """Fetch a directive from the mapping file, assuming the given plugin
        keyword and type.

        :param str directive: Name of the directive.
        :param str default: Value to return if directive not present.
        :param bool decodeWWJD: Whether to interpret the value as WWJD-encoded, and return the decoded value.
        :param bool asList: Whether to interpret value as a list. If true, then list elements are assumed to be space-delimited.
        :rtype: str, int, float, list, None
        """
        value = self.fetchWithPrefix(self._pluginKeyword, self._pluginType, directive)
        if value is None:
            return default
        if asList and isinstance(value, six.string_types):
            value = value.split()
            if decodeWWJD:
                value = [self.__session.decodeFromFMEParsableText(entry) for entry in value]
        elif decodeWWJD and isinstance(value, six.string_types):
            value = self.__session.decodeFromFMEParsableText(value)
        return value

    def getFlag(self, directive, default=False):
        """Get the specified directive and interpret it as a boolean value.

        :param str directive: Name of the directive.
        :param bool default: Value to return if directive not present.
        :rtype: bool
        """
        value = self.get(directive)
        if value is None:
            return default

        return fmeutil.stringToBool(value)

    def getSearchEnvelope(self):
        """Get the search envelope, with coordinate system, if any.

        :returns: The search envelope, or None if not set.
        :rtype: parsers.SearchEnvelope, None
        """
        env = self.mappingFile.fetchSearchEnvelope(self._pluginKeyword, self._pluginType)
        if not env:
            return None
        coordSys = self.get("_SEARCH_ENVELOPE_COORDINATE_SYSTEM")
        return SearchEnvelope(env, coordSys)

    def getFeatureTypes(self, openParameters, fetchMode=fmeconstants.kFME_FETCH_IDS_AND_DEFS):
        """Get the feature types, if any.

        :param list[str] openParameters: Parameters for the reader.
        :param int fetchMode: One of the valid feature type fetch modes from :mod:`fmegeneral.fmeconstants`.
        :returns: List of feature types, in Unicode.
        :rtype: list[six.text_type]
        """
        featTypes = self.mappingFile.fetchFeatureTypes(
            self._pluginKeyword, self._pluginType, openParameters, fetchMode
        )
        if featTypes is None:
            # Mapping file returns None when there are no feature types,
            # but that requires a separate check for None in code that uses it. Eliminate this distinction.
            return []
        return [systemToUnicode(ft) for ft in featTypes]


class FMETransformer(object):
    """Base class that represents the interface expected by the FME
    infrastructure for Python-based FME transformer implementations.

    This class can be used as a context manager.
    """

    def __init__(self):
        self.pyoutput_cb = None  # A pyoutput() implementation, for testing purposes.

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def input(self, feature):
        """Receive a feature from the transformer's input port.

        :type feature: FMEFeature
        """
        pass

    def process_group(self):
        """Called after all of the current group's features have been sent to input().
        Intended to perform group-by processing that requires knowledge of all features.
        Can be left unimplemented if group-by processing is not required.
        """
        pass

    def close(self):
        """Called at the end of translation."""
        pass

    def pyoutput(self, feature):
        """Emit a feature to one of the transformer's output ports.

        :type feature: FMEFeature
        """
        # Stub. Implementation is injected at runtime.
        if self.pyoutput_cb:
            self.pyoutput_cb(feature)

    def total_features_passed_along(self):
        """Returns a count of features that have been processed to date, in all groups"""
        # Stub. Implementation is injected at runtime.
        pass


class FMEEnhancedTransformer(FMETransformer):
    """Base class for Python-based FME transformer implementations.

    This class adds methods that introduce more granularity to the transformer execution lifecycle.

    :meth:`input` is broken down to:
       - :meth:`pre_input`
          - :meth:`setup` (first call only)
       - :meth:`receive_feature`
       - :meth:`post_input`

    :meth:`close` is broken down to:
       - :meth:`pre_close`
       - :meth:`finish`
       - :meth:`post_close`
    """

    def __init__(self):
        super(FMEEnhancedTransformer, self).__init__()
        self._initialized = False
        self._keyword = None
        try:
            debug = fme.macroValues.get("FME_DEBUG", False)
        except AttributeError:
            debug = False
        self._log = get_configured_logger(self.keyword, debug)

    @property
    def keyword(self):
        """Override this method to define the keyword identifying the
        transformer."""
        if not self._keyword:
            self._keyword = "Transformer"
        return self._keyword

    def setup(self, first_feature):
        """Override this method to perform operations upon the first call to
        :meth:`input`.

        :type first_feature: FMEFeature
        """
        pass

    def pre_input(self, feature):
        """Called before each :meth:`input`.

        :type feature: FMEFeature
        """
        if not self._initialized:
            self.setup(feature)
            self._initialized = True

    def receive_feature(self, feature):
        """Override this method instead of :meth:`input`.

        :type feature: FMEFeature
        """
        pass

    def post_input(self, feature):
        """Called after each :meth:`input`.

        :type feature: FMEFeature
        """
        pass

    def input(self, feature):
        """Do not override this method."""
        self.pre_input(feature)
        self.receive_feature(feature)
        self.post_input(feature)

    def pre_close(self):
        """Called before :meth:`close`."""
        pass

    def finish(self):
        """Override this instead of :meth:`close`."""
        pass

    def post_close(self):
        """Called after :meth:`close`."""
        pass

    def close(self):
        """Do not override this method."""
        self.pre_close()
        self.finish()
        self.post_close()

    def reject_feature(self, feature, code, reason):
        """Emit a feature to the transformer's rejection port."""
        feature.setAttribute(kFME_REJECTION_CODE, code)
        feature.setAttribute(kFME_REJECTION_MESSAGE, reason)
        self.pyoutput(feature)
