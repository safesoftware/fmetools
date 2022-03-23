# coding: utf-8

"""
FME PluginBuilder subclasses that provide improved functionality.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from fmeobjects import FMEFeature
from pluginbuilder import FMEReader, FMEWriter

from .logfile import get_configured_logger
from .parsers import OpenParameters, MappingFile


class FMESimplifiedReader(FMEReader):
    """Base class for Python-based FME reader implementations.

    :ivar str _type_name: The name used in the following contexts:

        * the name of the format's .db file in the formats info folder
        * the format short name for the format within the .db file
        * ``FORMAT_NAME`` in the metafile

    :ivar str _keyword: A unique identifier for this reader instance.
    :ivar MappingFile _mapping_file:
        Provides access into :class:`pluginbuilder.FMEMappingFile`.
    :ivar bool debug: Toggle for debug mode.
    :ivar logging.LoggerAdapter log: Provides access to the FME log.
    :ivar bool _using_constraints: True if :meth:`setConstraints` was called.
    :ivar bool _aborted: True if :meth:`abort` was called.
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

        self._log = None

        self._using_constraints = False
        self._aborted = False
        self._feature_types = []

        self._readSchema_generator, self._read_generator = None, None

    @property
    def log(self):
        """
        Provides access to the FME log.

        :rtype: logging.LoggerAdapter
        """
        if not self._log:
            # Instantiate a logger with the appropriate debug mode.
            self._log = get_configured_logger(self.__class__.__name__, self._debug)
        return self._log

    @property
    def debug(self):
        return self._debug

    @debug.setter
    def debug(self, new_debug):
        """
        Set the debug flag for this reader. Also changes the setting of the logger.
        """
        if new_debug != self._debug:
            self._debug = new_debug
            self._log = get_configured_logger(self.__class__.__name__, self._debug)

    def hasSupportFor(self, support_type):
        """
        Return whether this reader supports a certain type. Currently,
        the only supported type is fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM.

        When a reader supports fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM,
        a feature table object will be created from features produced by this reader.
        This will allow for significant performance gains if the reader will output
        a large number of features which share the same schema.
        To declare feature table shim support, the reader's metafile SOURCE_SETTINGS
        must also contain the line 'DEFAULT_VALUE CREATE_FEATURE_TABLES_FROM_DATA Yes'.

        :param int support_type: support type passed in by Workbench infrastructure
        :returns: True if the passed in support type is supported.
        :rtype: bool
        """
        return False

    def open(self, dataset_name, parameters):
        """Open the dataset for reading.

        Does these things for you:

        * Parses the open() parameters.
        * Checks for the debug flag in open() parameters.
        * Calls :meth:`enhancedOpen`.

        If setConstraints() wasn't called earlier, then this method also:
        * Sets `_feature_types` using the mapping file and/or open parameters.

        :param str dataset_name: Name of the dataset.
        :param list[str] parameters: List of parameters.
        """

        # If not using setConstraints(), then get some basics from the mapping file.
        if not self._using_constraints:
            self._feature_types = self._mapping_file.get_feature_types(parameters)

        # Look for the debug flag in the open() parameters.
        open_parameters = OpenParameters(dataset_name, parameters)
        if open_parameters.get("FME_DEBUG"):
            self._debug = True

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

        :param FMEFeature feature: The constraint feature.
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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FMESimplifiedWriter(FMEWriter):
    """Base class for Python-based FME writer implementations.

    :ivar str _type_name: The name used in the following contexts:

        * the name of the format's .db file in the formats info folder
        * the format short name for the format within the .db file
        * ``FORMAT_NAME`` in the metafile

    :ivar str _keyword: A unique identifier for this writer instance.
    :ivar MappingFile _mapping_file:
        Provides access into :class:`pluginbuilder.FMEMappingFile`.
    :ivar logging.LoggerAdapter log: Provides access to the FME log.
    :ivar bool debug: Toggle for debug mode.
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

        self._log = None

        self._aborted = False
        self._feature_types = []

    @property
    def log(self):
        """
        Provides access to the FME log
        """
        if not self._log:
            # Instantiate a logger with the appropriate debug mode.
            self._log = get_configured_logger(self.__class__.__name__, self._debug)
        return self._log

    @property
    def debug(self):
        return self._debug

    @debug.setter
    def debug(self, new_debug):
        """
        Set the debug flag for this writer. Also changes the setting of the logger.
        """
        if new_debug != self._debug:
            self._debug = new_debug
            self._log = get_configured_logger(self.__class__.__name__, self._debug)

    def open(self, dataset, parameters):
        """Open the dataset for writing.

        Does these things for you:

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
            self.debug = True

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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FMETransformer(object):
    """
    Base class that represents the interface expected by the FME
    infrastructure for Python-based FME transformer implementations.

    For testing purposes, this class can be used as a context manager.
    """

    def __init__(self):
        self.factory_name = self.__class__.__name__
        """
        The instantiating PythonFactory's ``FACTORY_NAME``.
        Defaults to the name of this class. Value is set by FME at runtime.
        """

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
        Called after all the current group's features have been sent to :meth:`input`.
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

    def total_features_passed_along(self):
        """
        Returns a count of features that have been processed to date, in all groups.

        :rtype: int
        """
        # Stub. Implementation is injected at runtime.
        pass

    def has_support_for(self, support_type):
        """
        Return whether this transformer supports a certain type. Currently,
        the only supported type is fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM.

        When a transformer supports fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM,
        FME will pass features to the transformer's :meth:`input` method that
        come from a feature table object. This will allow for significant performance
        gains when processing a large number of features.

        To support fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM, features passed
        into :meth:`input` can't be copied or cached for later use, and can't
        be read or modified after being passed to :meth:`pyoutput`. If any of
        those violations are performed, the behavior is undefined.

        A consequence of the fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM requirements
        is group-by processing is not possible in this mode because group-by
        processing requires caching of features for output in the :meth:`process_group`
        method.

        **Illegal Examples**

        *Copy and access later:* ::

            def input(self, feature):
                self._cached_features.append(feature)

            def close(self):
                for feature in self._cached_features:   # not allowed
                    self.pyoutput(feature)

        *Access after output:* ::

            def input(self, feature):
                self.pyoutput(feature)
                feature.setAttribute("attr name", "attr val")   # not allowed

        *Group-by processing:* ::

            def input(self, feature):
                self._cached_features.append(feature)

            def process_group(self):
                for feature in self._cached_features:   # not allowed
                    self.pyoutput(feature)

        **Note:** Support for this method and the fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM
        constant definition was added in FME 2022.0. For all earlier versions of
        FME, this method will never be called.

        :type support_type: int
        :returns: True if the passed in support type is supported.
        :rtype: bool
        """
        return False


class FMEEnhancedTransformer(FMETransformer):
    """
    Recommended base class for transformer implementations.

    This class adds methods to introduce more granularity to the transformer lifecycle.

    :meth:`input` is broken down to these methods for implementations to overwrite:
       - :meth:`pre_input`
          - :meth:`setup` - only called for the first input feature
       - :meth:`receive_feature` - should contain the bulk of the main logic
       - :meth:`post_input`

    :meth:`close` is broken down to these methods for implementations to overwrite:
       - :meth:`pre_close`
       - :meth:`finish` - should contain any cleanup tasks, such as deleting temp files
       - :meth:`post_close`

    Note that unlike readers and writers, transformers do not receive abort signals.
    """

    def __init__(self):
        super(FMEEnhancedTransformer, self).__init__()
        self._initialized = False
        self._log = None

    @property
    def log(self):
        """
        Provides access to the FME log.

        :rtype: logging.LoggerAdapter
        """
        if not self._log:
            self._log = get_configured_logger(self.factory_name)
        return self._log

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

    def reject_feature(self, feature, code, message):
        """
        Emit a feature, with conventional attributes that represent rejection.

        To work as intended, the transformer's FMX needs some corresponding lines:

        * `OUTPUT_TAGS` includes `<REJECTED>`. This defines the rejection port.
        * A `TestFactory` definition that sends features with
          the `fme_rejection_code` attribute to the rejection port.
        * Handling for the possibility of the transformer's initiator/input feature
          coming in with `fme_rejection_code` already defined.
          The transformer should not send features to the rejection port unless
          the feature was actually rejected by the transformer.
          If the input feature included rejection attributes,
          the transformer should pass them through in its output features.
          Of course, if the transformer happens to reject such a feature,
          it's free to overwrite those existing attributes.

        :param FMEFeature feature: Feature to emit, with rejection attributes added.
        :param str code: Value for `fme_rejection_code` attribute.
        :param str message: Value for `fme_rejection_message` attribute.
        """
        feature.setAttribute("fme_rejection_code", code)
        feature.setAttribute("fme_rejection_message", message)
        self.pyoutput(feature)
