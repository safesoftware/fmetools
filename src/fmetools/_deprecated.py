# coding: utf-8
"""This module includes any classes that have been deprecated."""
from typing import Optional

from fmeobjects import FMEFeature


class FMEBaseTransformer:
    """
    In FME 2024.2, this base class was deprecated and replaced with :class:`fme.BaseTransformer`.

    Base class that represents the interface expected by the FME
    infrastructure for Python-based transformer implementations.
    In particular, this is the class-based API required by the PythonFactory_::

        FACTORY_DEF {*} PythonFactory
            FACTORY_NAME { $(XFORMER_NAME) }
            INPUT { FEATURE_TYPE $(XFORMER_NAME)_READY }
            SYMBOL_NAME my_library.my_module.TransformerImpl
            OUTPUT { PYOUTPUT FEATURE_TYPE $(XFORMER_NAME)_PROCESSED }

    When executed by FME, this is approximately equivalent to::

        from my_library.my_module import TransformerImpl
        transformer = TransformerImpl()

    PythonFactory does not require Python classes to inherit from this base class,
    but it expects them to have the same interface as this class.

    This class can be used as a context manager to guarantee that :meth:`close` is called.
    This is useful for writing tests.

    .. seealso::

        PythonFactory_ in the `FME Factory and Function Documentation`_.

    .. _PythonFactory: https://docs.safe.com/fme/html/FME_FactFunc/doc_pages/pythonfactory.txt
    .. _FME Factory and Function Documentation: https://docs.safe.com/fme/html/FME_FactFunc/index.html
    """

    def __init__(self):
        """
        FME instantiates this class, so it must not require any constructor arguments.
        """
        self.factory_name: str = self.__class__.__name__
        """
        This is the ``FACTORY_NAME`` parameter of the PythonFactory_ that instantiated this class.
        Defaults to the name of this class.

        .. note::
            Do not modify this property. FME sets the value at runtime.

        .. _PythonFactory: https://docs.safe.com/fme/html/FME_FactFunc/doc_pages/pythonfactory.txt
        """

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def input(self, feature: FMEFeature) -> None:
        """
        Receive a feature from the transformer's single input port.

        This method is used instead of :meth:`input_from` if the transformer has no input tags,
        meaning that the transformer's INPUT_TAGS parameter is listed as <BLANK>.

        Transformers typically receive a feature through this method, process it,
        modify the feature by adding output attributes, and then output the feature using :meth:`pyoutput`.
        However, transformers may output any number of features for each input feature, or none at all.
        Transformers may also create new :class:`FMEFeature` instances and output them.

        :param feature: The feature to process.
        """
        pass

    def input_from(self, feature: FMEFeature, input_tag: str) -> None:
        """
        Receive a feature from input_tag.

        This method is used instead of :meth:`input` if the transformer has defined input tags
        listed in the transformer's INPUT_TAGS parameter and the PythonFactory's
        PY_INPUT_TAGS clause. Introduced in FME 2024.0.

        Example of a ``PythonFactory`` definition with two input tags::

            FACTORY_DEF {*} PythonFactory
                FACTORY_NAME { $(XFORMER_NAME) }
                PY_INPUT_TAGS { INPUT0 INPUT1 }
                $(INPUT_LINES)
                SYMBOL_NAME { symbol_name }
                PY_OUTPUT_TAGS { Output <Rejected> }
                OUTPUT { Output FEATURE_TYPE $(OUTPUT_Output_FTYPE)
                    $(OUTPUT_Output_FUNCS) }
                OUTPUT { <Rejected> FEATURE_TYPE $(OUTPUT_<Rejected>_FTYPE)
                    $(OUTPUT_<Rejected>_FUNCS) }

        Transformers typically receive a feature through this method, process it,
        modify the feature by adding output attributes, and then output the feature using :meth:`pyoutput`.
        However, transformers may output any number of features for each input feature, or none at all.
        Transformers may also create new :class:`FMEFeature` instances and output them.

        :param feature: The feature to process.
        :param input_tag: The input tag that feature came from.
        """
        pass

    def process_group(self) -> None:
        """
        If group processing is enabled, then this is called after all the
        current group's features have been sent to :meth:`input`.
        Can be left unimplemented if group processing is not supported.

        :meth:`pyoutput` may be called from this method.
        """
        pass

    def close(self) -> None:
        """
        Called at the end of translation.
        Override this method to perform any necessary cleanup or finalization operations.

        :meth:`pyoutput` may be called from this method.
        """
        pass

    def pyoutput(self, feature: FMEFeature, output_tag: Optional[str] = None) -> None:
        """
        Output a feature from the transformer to an output tag. If an output tag is specified and does not exist on
        the PythonFactory, an error will be raised.

        .. note::
            Do not implement this method. FME injects the implementation at runtime.

        :param feature: The feature to output.
        :param output_tag: The output tag to direct feature to. If multiple output tags exist but this argument is not
            specified, ``PYOUTPUT`` will be used as a fallback value. If the PythonFactory definition has a single
            output tag, this tag will be the default. Introduced in FME 2024.0.
        """
        # Stub. Implementation is injected at runtime.

    def total_features_passed_along(self) -> int:
        """
        .. note::
            Do not implement this method. FME injects the implementation at runtime.

        :returns: A count of features that have been processed to date, in all groups.
        """
        # Stub. Implementation is injected at runtime.
        pass

    # noinspection PyMethodMayBeStatic
    def has_support_for(self, support_type: int) -> bool:
        """
        .. versionadded:: 2022.0
            This method and its corresponding constants in :mod:`fmeobjects`.

        This method is used by FME to check whether the transformer claims support for certain capabilities.
        Currently, the only supported type is :data:`fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM`,
        which determines support for Bulk Mode.

        **Why support Bulk Mode**

        When a transformer supports Bulk Mode,
        FME may pass features to :meth:`input` that come from a feature table object.
        This allows significant performance gains when processing many features,
        but requires the transformer to follow certain rules around how it handles features.

        .. seealso:: `How FME Improves Performance with Bulk Mode <https://docs.safe.com/fme/html/FME-Form-Documentation/FME-Form/Workbench/Improving-Performance-Bulk-Mode.htm>`_.

        **How to support Bulk Mode**

        * Features received by :meth:`input` must not be copied or cached for later use.
        * Features received by :meth:`input` must not be read or modified after being passed to :meth:`pyoutput`.
        * :meth:`pyoutput` should not be given new :class:`FMEFeature` instances.
          Doing so will automatically downgrade feature processing to individual mode.
        * Override this method. When ``support_type`` is :data:`fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM`,
          return ``True``.

        Violating these requirements may result in undefined behavior.

        **Illegal Examples**

        *Copy and access later:* ::

            def input(self, feature):
                self._cached_features.append(feature)

            def close(self):
                for feature in self._cached_features:  # not allowed
                    self.pyoutput(feature)

        *Access after output:* ::

            def input(self, feature):
                self.pyoutput(feature)
                feature.setAttribute("attr name", "attr val")  # not allowed

        *Group-by processing:* ::

            def input(self, feature):
                self._cached_features.append(feature)

            def process_group(self):
                for feature in self._cached_features:  # not allowed
                    self.pyoutput(feature)

        :param support_type: The type of support to check for.
            Currently, the only supported type is :data:`fmeobjects.FME_SUPPORT_FEATURE_TABLE_SHIM`.
        :returns: ``True`` if the passed in support type is supported.
            The default implementation returns ``False``.
        """
        return False
