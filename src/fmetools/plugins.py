# coding: utf-8

"""
This module provides base classes for FME plugins such as transformers.

:class:`FMEEnhancedTransformer` is the recommended base class for transformers.
Transformer developers should subclass it to implement their own transformers.
"""

from __future__ import annotations

import logging
import warnings
from typing import Optional, Generator

try:
    from fme import BaseTransformer as FMEBaseTransformer
except ImportError:  # Support < FME 2024.2
    from ._deprecated import FMEBaseTransformer

from fmeobjects import FMEFeature

try:
    from fmeobjects import FME_SUPPORT_FEATURE_TABLE_SHIM
except ImportError:  # Support < FME 2022.0 b22235
    FME_SUPPORT_FEATURE_TABLE_SHIM = 0

from pluginbuilder import FMEReader, FMEWriter

from .logfile import get_configured_logger
from .parsers import MappingFile, OpenParameters

# These are relevant externally.
# Reader and writer base classes are omitted because they're not intended for general use.
__all__ = [
    "FMEEnhancedTransformer",
]


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
    :ivar bool _list_feature_types: True if the reader was launched to produce
        a list of feature types.
    :ivar _readSchema_generator:
        Use this member to store any generator used for :meth:`readSchema`.
       Doing so means it'll be explicitly closed for you in :meth:`close`.
    :ivar _read_generator:
        Use this member to store any generator used for :meth:`read`.
        Doing so means it'll be explicitly closed for you in :meth:`close`.
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

        self._list_feature_types = False

        self._readSchema_generator, self._read_generator = None, None

    @property
    def log(self) -> logging.LoggerAdapter:
        """Provides access to the FME log."""
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

    def hasSupportFor(self, support_type) -> bool:
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

    def open(self, dataset_name, parameters) -> None:
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

        self._list_feature_types = self._mapping_file.get_flag(
            "RETRIEVE_ALL_TABLE_NAMES"
        )

        return self.enhancedOpen(open_parameters)

    def enhancedOpen(self, open_parameters) -> None:
        """
        Implementations shall override this method instead of :meth:`open`.

        :param OpenParameters open_parameters: Parameters for the reader.
        """
        pass

    def setConstraints(self, feature) -> None:
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

    def _feature_types_generator(self) -> Generator[FMEFeature]:
        """
        A generator which produces features for each potential feature type from
        the reader's dataset.

        The feature types will populate the list displayed by the GUI Type FEATURE_TYPES.

        Must yield FMEFeatures with the feature type set.
        Only the feature type is required; feature attributes will be ignored.
        """
        pass

    def _schema_features_generator(self) -> Generator[FMEFeature]:
        """
        A generator which produces schema features for all requested feature types.

        When `self._feature_types` is empty, schema features for all possible
        feature types should be generated. Otherwise, a single schema feature
        should be generated for each feature type in `self._feature_types`.

        The function :meth:`features.build_feature` should be used to create schema features.
        Schema features must contain the feature type, all possible geometry
        types for the feature type, and exposed attributes for the feature.
        The attribute value for a schema attribute should be set to the expected
        format attribute type.
        """
        pass

    def readSchema(self) -> Optional[FMEFeature]:
        """
        Creates schema features.

        Implementations should override :meth:`_feature_types_generator`
        and :meth:`_schema_features_generator` instead of this method.
        """
        # pylint: disable=invalid-name
        if not self._readSchema_generator:
            if self._list_feature_types:
                self._readSchema_generator = self._feature_types_generator()
            else:
                self._readSchema_generator = self._schema_features_generator()
        try:
            return next(self._readSchema_generator)
        except StopIteration:
            return None

    def readSchemaGenerator(self) -> Generator[FMEFeature]:
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

    def _read_features_generator(self) -> Generator[FMEFeature]:
        """
        Generator which yields data features for all requested feature types.

        The function :meth:`features.build_feature` should be used to create data features.
        """
        pass

    def read(self) -> Optional[FMEFeature]:
        """
        Creates features for a feature type.

        Implementations should override :meth:`_read_features_generator`
        instead of this method.
        """
        # pylint: disable=invalid-name
        if not self._read_generator:
            self._read_generator = self._read_features_generator()

        try:
            return next(self._read_generator)
        except StopIteration:
            return None

    def readGenerator(self) -> Generator[FMEFeature]:
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

    def abort(self) -> None:
        self._aborted = True

    def close(self) -> None:
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


class FMETransformer(FMEBaseTransformer):
    """
    In FME versions prior to 2024.2, this will subclass :class:`fmetools._deprecated.FMEBaseTransformer`
    instead.
    """

    def __init__(self):
        super().__init__()
        warnings.warn(
            "Avoid confusion with fmeobjects.FMETransformer", DeprecationWarning
        )


class FMEEnhancedTransformer(FMEBaseTransformer):
    """
    This is the recommended base class for transformer implementations.
    It exposes the FME log file through the :attr:`log` property,
    and adds methods to introduce more granularity to the transformer lifecycle
    to help developers organize their code.

    In FME versions prior to 2024.2, this will subclass :class:`fmetools._deprecated.FMEBaseTransformer`
    instead.

    :meth:`input` is broken down to these methods for implementations to overwrite:
       - :meth:`pre_input`
          - :meth:`setup` which is only called for the first input feature
       - :meth:`receive_feature` which should contain the bulk of the main logic
       - :meth:`post_input`

    :meth:`input_from` is broken down to these methods for implementations to overwrite:
       - :meth:`pre_input_from`
          - :meth:`setup_from` which is only called for the first input feature from each input tag
       - :meth:`receive_feature_from` which should contain the bulk of the main logic
       - :meth:`post_input_from`

    :meth:`close` is broken down to these methods for implementations to overwrite:
       - :meth:`pre_close`
       - :meth:`finish` which should contain any cleanup tasks
       - :meth:`post_close`

    **A typical transformer would implement:**

        - :meth:`setup` or :meth:`setup_from` to collect constant transformer parameters off the first input feature
          and use them to do any initialization steps.
        - :meth:`receive_feature` or :meth:`receive_feature_from` to process each input feature.
        - :meth:`finish` to delete any temporary files or close any connections.

    .. note::

        This class overrides :meth:`has_support_for` to return ``True`` for Bulk Mode support.
        This means that the transformer cannot cache or copy features for later use,
        and cannot output new :class:`fmeobjects.FMEFeature` instances.
        See :meth:`fme.BaseTransformer.has_support_for` for details about these restrictions.
    """

    def __init__(self):
        super(FMEEnhancedTransformer, self).__init__()
        self._initialized = False
        self._initialized_tags = set()
        self._log = None

    @property
    def log(self) -> logging.LoggerAdapter:
        """
        Provides access to the FME log.
        """
        if not self._log:
            self._log = get_configured_logger(self.factory_name)
        return self._log

    def setup(self, first_feature: FMEFeature) -> None:
        """
        This method is only called for the first input feature.
        Implement this method to perform any necessary setup operations,
        such as getting constant parameters.

        Constant parameters are ones that cannot change across input features.
        For parameters defined using GUI Types, these are ones that do not include ``OR_ATTR``.
        For parameters defined with Transformer Designer,
        these are ones with Value Type Level not set to "Full Expression Support".

        :param first_feature: First input feature.
        """
        pass

    def pre_input(self, feature: FMEFeature) -> None:
        """
        Called before each :meth:`input`.
        """
        if not self._initialized:
            self.setup(feature)
            self._initialized = True

    def receive_feature(self, feature: FMEFeature) -> None:
        """
        Override this method instead of :meth:`input`.
        This method receives all input features, including the first one that's also passed to :meth:`setup`.
        """
        pass

    def post_input(self, feature: FMEFeature) -> None:
        """
        Called after each :meth:`input`.
        """
        pass

    def input(self, feature: FMEFeature) -> None:
        """Do not override this method."""
        self.pre_input(feature)
        self.receive_feature(feature)
        self.post_input(feature)

    def setup_from(self, first_feature: FMEFeature, input_tag: str) -> None:
        """
        This method is only called for the first input feature from each unique input tag.
        Implement this method to perform any necessary setup operations,
        such as getting constant parameters.

        Constant parameters are ones that cannot change across input features.
        For parameters defined using GUI Types, these are ones that do not include ``OR_ATTR``.
        For parameters defined with Transformer Designer,
        these are ones with Value Type Level not set to "Full Expression Support".

        :param first_feature: First input feature.
        :param input_tag: Input tag that first_feature came from.
        """
        pass

    def pre_input_from(self, feature: FMEFeature, input_tag: str) -> None:
        """
        Called before each :meth:`input_from`.
        """
        if input_tag not in self._initialized_tags:
            self.setup_from(feature, input_tag)
            self._initialized_tags.add(input_tag)

    def receive_feature_from(self, feature: FMEFeature, input_tag: str) -> None:
        """
        Override this method instead of :meth:`input_from`.
        This method receives all input features from input_tag, including the first one that's also
        passed to :meth:`setup_from`.
        """
        pass

    def post_input_from(self, feature: FMEFeature, input_tag: str) -> None:
        """
        Called after each :meth:`input_from`.
        """
        pass

    def input_from(self, feature: FMEFeature, input_tag: str) -> None:
        """Do not override this method."""
        self.pre_input_from(feature, input_tag)
        self.receive_feature_from(feature, input_tag)
        self.post_input_from(feature, input_tag)

    def pre_close(self) -> None:
        """Called before :meth:`close`."""
        pass

    def finish(self) -> None:
        """Override this instead of :meth:`close`."""
        pass

    def post_close(self) -> None:
        """Called after :meth:`close`."""
        pass

    def close(self) -> None:
        """Do not override this method."""
        self.pre_close()
        self.finish()
        self.post_close()

    def reject_feature(self, feature: FMEFeature, code: str, message: str) -> None:
        """
        Output a feature with conventional attributes that represent rejection.

        Method will first attempt to output to ``<Rejected>``. If the ``<Rejected>`` tag doesn't exist on the
        ``PythonFactory`` definition, then feature will be directed to ``PYOUTPUT``.

        For transformers that only support FME 2024.0+, the transformer definition file should:

        * Specify a ``PY_OUTPUT_TAGS`` clause in the ``PythonFactory`` definition
        * Add ``<Rejected>`` to ``OUTPUT_TAGS`` and ``PY_OUTPUT_TAGS``
        * Specify ``<Rejected>`` output tag in the ``PythonFactory`` definition

        Example of a ``PythonFactory`` definition for a transformer with two output ports::

            FACTORY_DEF {*} PythonFactory
                FACTORY_NAME { $(XFORMER_NAME) }
                $(INPUT_LINES)
                SYMBOL_NAME { symbol_name }
                PY_OUTPUT_TAGS { Output <Rejected> }
                OUTPUT { Output FEATURE_TYPE $(OUTPUT_Output_FTYPE)
                    $(OUTPUT_Output_FUNCS) }
                OUTPUT { <Rejected> FEATURE_TYPE $(OUTPUT_<Rejected>_FTYPE)
                    $(OUTPUT_<Rejected>_FUNCS) }

        To support versions earlier than FME 2024.0, the transformer definition file needs to specify a
        ``<Rejected>`` output port, and its Execution Instructions need some corresponding lines:

        * A ``TestFactory`` definition that sends features with
          the ``fme_rejection_code`` attribute to the rejection port.
        * Handling for the possibility of the transformer's initiator/input feature
          coming in with ``fme_rejection_code`` already defined.
          The transformer should not send features to the rejection port unless
          the feature was actually rejected by the transformer.
          If the input feature included rejection attributes,
          the transformer should pass them through in its output features.
          If the transformer happens to reject such a feature,
          it's free to overwrite those existing attributes.

        Example of a ``PythonFactory`` and ``TestFactory`` definition for a transformer with two output ports::

            FACTORY_DEF {*} PythonFactory
                FACTORY_NAME { $(XFORMER_NAME) }
                INPUT { FEATURE_TYPE $(XFORMER_NAME)_READY }
                SYMBOL_NAME { symbol_name }
                OUTPUT { PYOUTPUT FEATURE_TYPE $(XFORMER_NAME)_PROCESSED }

            # Removed all internal-prefixed attributes from output feature
            # and emit to the correct output port based on value of fme_rejection_code.
            FACTORY_DEF {*} TestFactory
                FACTORY_NAME { $(XFORMER_NAME)_ROUTER }
                INPUT { FEATURE_TYPE $(XFORMER_NAME)_PROCESSED }
                TEST &fme_rejection_code == ""
                OUTPUT { PASSED FEATURE_TYPE $(OUTPUT_Output_FTYPE)
                    @RenameAttributes(FME_STRICT,fme_rejection_code,___fme_rejection_code___)
                    @RemoveAttributes(fme_regexp_match,^<internal prefix>.*$)
                    $(OUTPUT_Output_FUNCS) }
                OUTPUT { FAILED FEATURE_TYPE $(OUTPUT_<REJECTED>_FTYPE)
                    @RemoveAttributes(___fme_rejection_code___)
                    @RemoveAttributes(fme_regexp_match,^<internal prefix>.*$)
                    $(OUTPUT_<REJECTED>_FUNCS) }

        :param feature: Feature to reject.
            Rejection attributes are added to this feature.
            Then it is passed to :meth:`pyoutput`.
        :param code: Value for the ``fme_rejection_code`` attribute.
        :param message: Value for the ``fme_rejection_message`` attribute.
        """
        feature.setAttribute("fme_rejection_code", code)
        feature.setAttribute("fme_rejection_message", message)

        try:
            self.pyoutput(feature, output_tag="<Rejected>")
        except TypeError:
            # For backwards compatibility. Output to the default output tag for the transformer definition to redirect
            # the feature to the `<Rejected>` tag.
            self.pyoutput(feature)

    def has_support_for(self, support_type: int) -> bool:
        """
        Overrides the default implementation to report support for Bulk Mode.

        :returns: ``True`` if ``support_type`` is :data:`fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM`.
            See :meth:`fme.BaseTransformer.has_support_for` for more details.
        """
        if support_type == FME_SUPPORT_FEATURE_TABLE_SHIM:
            return True
        return super().has_support_for(support_type)
