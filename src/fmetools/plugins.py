"""
FME PluginBuilder subclasses that provide improved functionality.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import fme
from fmeobjects import FMEFeature
from pluginbuilder import FMEReader, FMEWriter

from fmetools.fmelog import get_configured_logger
from fmetools.parsers import OpenParameters, MappingFile


class FMESimplifiedReader(FMEReader):
    """Base class for Python-based FME reader implementations.

    :ivar str _type_name: The name used in the following contexts:

        * the name of the format's .db file in the formats info folder
        * the format short name for the format within the .db file
        * ``FORMAT_NAME`` in the metafile

    :ivar str _keyword: A unique identifier for this reader instance.
    :ivar MappingFile _mapping_file:
        Provides access into :class:`pluginbuilder.FMEMappingFile`.
    :ivar bool _debug: Toggle for debug mode.
    :ivar FMELoggerAdapter _log: Provides access to the FME log.
    :ivar bool _using_constraints: True if :meth:`setConstraints` was called.
    :ivar bool _aborted: True if :meth:`abort` was called.
    :ivar SearchEnvelope _search_envelope:
        Rectangular search envelope, if any, from the mapping file.
    :ivar list[str] _feature_types: Ordered list of feature type names.
    :ivar _readSchema_generator:
        Use this member to store any generator used for :meth:`readSchema`.
       Doing so means it'll be be explicitly closed for you in :meth:`close`.
    :ivar _read_generator:
        Use this member to store any generator used for :meth:`read`.
        Doing so means it'll be be explicitly closed for you in :meth:`close`.
        :meth:`setConstraints` will both close it and set it to `None`.
        This means :meth:`read` can just check this member for `None` to determine
        whether it needs to re-instantiate its generator to honour new settings.
    """

    def __init__(self, reader_type_name, reader_keyword, mapping_file):
        # super() is intentionally not called. Base class disallows it.
        self._type_name = reader_type_name
        self._keyword = reader_keyword
        self._mapping_file = MappingFile(mapping_file, reader_keyword, reader_type_name)

        # Check if the debug flag is set
        self._debug = self._mapping_file.mapping_file.fetch("FME_DEBUG") is not None

        # Instantiate a logger with the appropriate debug mode.
        self._log = get_configured_logger(self.__class__.__name__, self._debug)

        self._using_constraints = False
        self._aborted = False
        self._search_envelope = None
        self._feature_types = []

        self._readSchema_generator, self._read_generator = None, None

    def open(self, dataset_name, parameters):
        """Open the dataset for reading.

        Does these things for you:

        * Parses the open() parameters.
        * Checks for the debug flag in open() parameters.
        * Calls :meth:`enhancedOpen`.

        If setConstraints() wasn't called earlier, then this method also:
        * Sets `_search_envelope` using the mapping file.
        * Sets `_feature_types` using the mapping file and/or open parameters.

        :param str dataset_name: Name of the dataset.
        :param list[str] parameters: List of parameters.
        """

        # If not using setConstraints(), then get some basics from the mapping file.
        if not self._using_constraints:
            self._search_envelope = self._mapping_file.get_search_envelope()
            self._feature_types = self._mapping_file.get_feature_types(parameters)

        # Look for the debug flag in the open() parameters.
        open_parameters = OpenParameters(dataset_name, parameters)
        if open_parameters.get("FME_DEBUG"):
            self._debug = True
            self._log = get_configured_logger(self.__class__.__name__, self._debug)

        return self.enhancedOpen(open_parameters)

    def enhancedOpen(self, open_parameters):
        """
        Implementations shall override this method instead of :meth:`open`.

        :param OpenParameters open_parameters: Parameters for the reader.
        """
        pass

    def setConstraints(self, feature):
        """
        Reset any existing feature generator that represents the state for :meth:`read`.

        :param fmeobjects.FMEFeature feature: The constraint feature.
        """
        assert isinstance(feature, FMEFeature)
        self._using_constraints = True

        # Reset any existing feature generator that represents the state for read().
        if self._read_generator is not None:
            self._read_generator.close()
            self._read_generator = None

    def readSchemaGenerator(self):
        """
        Generator form of :meth:`readSchema`.

        Simplifies some logic in tests by eliminating the need to
        check whether the return value is `None`.
        """
        while True:
            feature = self.readSchema()
            if feature:
                yield feature
            else:
                break

    def readGenerator(self):
        """
        Generator form of :meth:`read`.

        Simplifies some logic in tests by eliminating the need to
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
        """
        This default implementation closes any existing read generators.
        """
        # If the reader is closed prior to the generators being exhausted,
        # the generators must be closed explicitly,
        # or else FMESession may leak and cause warnings.
        # This can happen during a runtime error that causes abort() to be called,
        # or if Features to Read was set in the workspace, which limits read() calls.
        if self._readSchema_generator:
            self._readSchema_generator.close()
        if self._read_generator:
            self._read_generator.close()


class FMESimplifiedWriter(FMEWriter):
    """Base class for Python-based FME writer implementations.

    :ivar str _type_name: The name used in the following contexts:

        * the name of the format's .db file in the formats info folder
        * the format short name for the format within the .db file
        * ``FORMAT_NAME`` in the metafile

    :ivar str _keyword: A unique identifier for this writer instance.
    :ivar MappingFile _mapping_file:
        Provides access into :class:`pluginbuilder.FMEMappingFile`.
    :ivar FMELoggerAdapter _log: Provides access to the FME log.
    :ivar bool _debug: Toggle for debug mode.
    :ivar bool _aborted: True if :meth:`abort` was called.
    :ivar list[str] _feature_types: Ordered list of feature types.
    """

    def __init__(self, writer_type_name, writer_keyword, mapping_file):
        # super() is intentionally not called. Base class disallows it.
        self._type_name = writer_type_name
        self._keyword = writer_keyword
        self._mapping_file = MappingFile(mapping_file, writer_keyword, writer_type_name)

        # Check if the debug flag is set
        self._debug = self._mapping_file.mapping_file.fetch("FME_DEBUG") is not None

        # Instantiate a logger with the appropriate debug mode.
        self._log = get_configured_logger(self.__class__.__name__, self._debug)

        self._aborted = False
        self._searchEnvelope = None
        self._feature_types = []

    def open(self, dataset, parameters):
        """Open the dataset for writing.

        Does these things for you:

        * Sets `_search_envelope` using the mapping file.
        * Sets `_feature_types` using the mapping file and/or open parameters.
        * Parses the open() parameters.
        * Checks for the debug flag in open() parameters,
          switching `_logger` to debug mode if present.
        * Calls :meth:`enhancedOpen`.

        :param str dataset: Dataset value, such as a file path or URL.
        :param list[str] parameters: List of parameters.
        """

        self._feature_types = self._mapping_file.get_feature_types(parameters)

        # Look for the debug flag in the open() parameters.
        open_parameters = OpenParameters(dataset, parameters)
        if open_parameters.get("FME_DEBUG"):
            self._debug = True
            self._log = get_configured_logger(self.__class__.__name__, self._debug)

        return self.enhancedOpen(open_parameters)

    def enhancedOpen(self, open_parameters):
        """
        Implementations shall override this method instead of :meth:`open`.

        :param OpenParameters open_parameters: Parameters for the writer.
        """
        pass

    def abort(self):
        self._aborted = True

    def close(self):
        """
        This default implementation does nothing.

        It's defined here because :class:`pluginbuilder.FMEWriter` requires it to be
        overridden.
        """
        pass


class FMETransformer(object):
    """
    Base class that represents the interface expected by the FME
    infrastructure for Python-based FME transformer implementations.

    For testing purposes, this class can be used as a context manager.
    """

    def __init__(self):
        self.pyoutput_cb = None  # A pyoutput() implementation, for testing purposes.

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def input(self, feature):
        """
        Receive a feature from the transformer's input port.

        :type feature: FMEFeature
        """
        pass

    def process_group(self):
        """
        Called after all of the current group's features have been sent to input().
        Intended to perform group-by processing that requires knowledge of all features.
        Can be left unimplemented if group-by processing is not required.
        """
        pass

    def close(self):
        """Called at the end of translation."""
        pass

    def pyoutput(self, feature):
        """
        Emit a feature to one of the transformer's output ports.

        :type feature: FMEFeature
        """
        # Stub. Implementation is injected at runtime.
        if self.pyoutput_cb:
            self.pyoutput_cb(feature)

    def total_features_passed_along(self):
        """
        Returns a count of features that have been processed to date, in all groups.

        :rtype: int
        """
        # Stub. Implementation is injected at runtime.
        pass


class FMEEnhancedTransformer(FMETransformer):
    """
    Recommended base class for transformer implementations.

    This class adds methods to introduce more granularity to the transformer lifecycle.

    :meth:`input` is broken down to:
       - :meth:`pre_input`
          - :meth:`setup` (first call only)
       - :meth:`receive_feature`
       - :meth:`post_input`

    :meth:`close` is broken down to:
       - :meth:`pre_close`
       - :meth:`finish`
       - :meth:`post_close`

    :ivar FMELoggerAdapter _log: Provides access to the FME log.
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
        """
        Override this method to perform operations upon the first call to
        :meth:`input`.

        :type first_feature: FMEFeature
        """
        pass

    def pre_input(self, feature):
        """
        Called before each :meth:`input`.

        :type feature: FMEFeature
        """
        if not self._initialized:
            self.setup(feature)
            self._initialized = True

    def receive_feature(self, feature):
        """
        Override this method instead of :meth:`input`.

        :type feature: FMEFeature
        """
        pass

    def post_input(self, feature):
        """
        Called after each :meth:`input`.

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
        feature.setAttribute("fme_rejection_code", code)
        feature.setAttribute("fme_rejection_message", reason)
        self.pyoutput(feature)
