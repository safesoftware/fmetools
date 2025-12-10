"""
This module provides :class:`TransformerParameterParser`,
the recommended way to access transformer parameter values.

.. warning::
    This module requires:

    - FME Form 2023 b23224 or newer
    - FME Flow 2024 b24145 or newer

    Packages using this module and targeting both FME Form and FME Flow
    should set ``minimum_fme_build`` in its package.yml accordingly.
"""

from __future__ import annotations

import itertools
from enum import Enum
from functools import lru_cache
from typing import Any, Iterable, Optional, Union

from fmetools.features import get_attribute

try:
    from fmeobjects import FMEException, FMEFeature, FMETransformer
except ModuleNotFoundError as e:
    raise ModuleNotFoundError(str(e) + " (introduced in FME 2023 b23224)")


_MISSING = object()


class ParameterState(str, Enum):
    """Special sentinel values for transformer parameters."""

    NULL = "FME_NULL_VALUE"
    """The parameter value is null."""
    NO_OP = "_FME_NO_OP_"
    """The parameter value is 'no-op'."""


_parameter_state_values = {
    item.value for item in ParameterState
}  # `x in ParameterState` needs PY>=3.12.
ParsedParameterType = Union[str, int, float, list, bool, ParameterState, None]
"""All possible types for parsed transformer parameter values."""


class _ParameterValuesCache:
    def __init__(self, xformer: FMETransformer):
        self._xformer = xformer
        self._cache = lru_cache(typed=True)(self._get)

    def _get(self, name: str, unparsed_value: Any) -> ParsedParameterType:
        # Method args form the key for lru_cache;
        # method body doesn't need to use unparsed_value.
        if unparsed_value is None:
            return None
        return self._xformer.getParsedParamValue(name)

    def get(self, name: str, unparsed_value: Any) -> ParsedParameterType:
        return self._cache(name, unparsed_value)


class TransformerParameterParser:
    """
    Helper for getting parsed transformer parameter values.

    .. warning::
        Instantiating this class on FME Flow requires FME Flow b24145 or newer.
        Instantiating the class on older versions of FME Flow will raise an exception.

    All parameters of Python transformers are set as attributes on input features.
    By convention, these attributes are given a prefix to give it a namespace and
    signify that they are internal attributes.
    The values of these attributes are string serializations that need to be deserialized before use.

    This parser works by loading a transformer definition from FME,
    passing it serialized parameter values from an input feature,
    and then requesting deserialized values back.
    FME uses the transformer definition to determine how to deserialize the values.

    A typical workflow using this parser:

    1. **Set the parameters as attributes on input features.**
       This is done in the transformer definition's Execution Instructions.
       The recommended way to do this is to use ``$(FME_PARM_VAL_LIST)`` in the TeeFactory preceding the PythonFactory:

        .. code-block:: text

            FACTORY_DEF {*} TeeFactory
            FACTORY_NAME { $(XFORMER_NAME)_CATCHER }
            $(INPUT_LINES)
            OUTPUT { FEATURE_TYPE $(XFORMER_NAME)_READY
                $(FME_PARM_VAL_LIST)
            }

       This sets all visible parameters of the transformer as attributes on every input feature.

    2. **Instantiate this parser as an instance member** of the class that implements the transformer.
       If a version isn't specified, then the latest version of the transformer definition is loaded.
    3. **Load a specific transformer version if needed.**
       If the transformer has multiple versions defined,
       and the latest version is incompatible with parameters from older versions,
       then change to the desired version of the transformer.

       If the transformer implementation needs to be aware of the version of the transformer definition,
       then supply the version number as an internal attribute on the input feature.
       This can be done by opening the transformer version's Execution Instructions and
       editing the TeeFactory to add the internal attribute:

        .. code-block:: text

            FACTORY_DEF {*} TeeFactory
            FACTORY_NAME { $(XFORMER_NAME)_CATCHER }
            $(INPUT_LINES)
            OUTPUT { FEATURE_TYPE $(XFORMER_NAME)_READY
                @SupplyAttributes(___XF_VERSION, 1)
                $(FME_PARM_VAL_LIST)
            }

       Then load the desired transformer version by calling :meth:`change_version`.
       Since this would only happen upon receiving the first input feature,
       implement this in :meth:`fmetools.plugins.FMEEnhancedTransformer.setup`.
       For instance:

        .. code-block:: python

            def setup(self, feature: FMEFeature):
                super().setup(feature)
                self.parser.change_version(feature.getAttribute("___XF_VERSION"))

    4. **Do a one-time gathering of fixed parameter values from the input feature.**
       For parameters that are known to be constant for the lifetime of the transformer,
       parse them once and cache their values. For instance:

        .. code-block:: python

            def setup(self, feature: FMEFeature):
                super().setup(feature)
                self.parser.set_all(feature)  # Collects all ___XF_ prefixed attributes by default
                self.sender = self.parser.get("SENDER")  # Assumes ___XF_ prefix by default
                self.mail_server = self.parser.get("MAIL_SERVER")

    5. **Get variable parameter values from every input feature.**
       For every input feature, call :meth:`set_all` to update the parameter values
       before calling :meth:`get` to get their parsed values.

       .. code-block:: python

            def receive_feature(self, feature: FMEFeature):
                super().receive_feature(feature)
                self.parser.set_all(feature)  # Collects all ___XF_ prefixed attributes by default

                send_email(
                    server=self.mail_server, from=self.sender,
                    to=self.parser.get("RECIPIENT"),  # Assumes ___XF_ prefix by default
                    subject=self.parser.get("SUBJECT"),
                    body=self.parser.get("BODY"),
                )
                self.pyoutput(feature)
    """

    xformer: FMETransformer
    """Instance for parameter value parsing."""
    transformer_name: str
    """Unqualified name of the transformer."""
    transformer_fpkg: Optional[str]
    """Empty for non-packaged transformers."""
    _last_seen_value: dict[str, Any]
    """param name -> most recently seen unparsed value. :meth:`set_all` updates this to reflect the latest feature."""
    _is_required_cache: dict[str, bool]
    """param name -> whether the parameter is required or enabled."""
    _parsed_values_cache: _ParameterValuesCache
    """Cache of parsed parameter values."""

    def __init__(
        self,
        transformer_name: str,
        version: Optional[int] = None,
    ):
        """
        :param transformer_name: Fully-qualified name of the transformer.
            For example, ``my_publisher.my_package.MyTransformer``.
            Note that this is the name of the transformer in FME,
            not the name of the Python class that implements it.

            The transformer may be defined in the FMX and FMXJ formats.
        :param version: Transformer version to load.
            If not provided, then the latest version is loaded.
        :raises ValueError: If FME cannot find the specified transformer.
        """
        # If the given name is foo.bar.baz, then first try using foo.bar as
        # the fmePackageName argument, for better performance.
        # Fully-qualified package name is still required.
        # FMETransformer will also take the fully-qualified name without
        # the fmePackageName argument, but it's slower.
        resolve = [(transformer_name, "")]
        name_parts = transformer_name.split(".", maxsplit=2)
        if len(name_parts) == 3:
            resolve.insert(0, (transformer_name, ".".join(name_parts[:2])))
        if version is None:
            version = -1

        for i, value in enumerate(resolve):
            name, pkg = value
            try:
                # FMETransformer was added in b23224.
                # Before b23264, it accepted but ignored kwargs. (FMEENGINE-77074)
                # For max compatibility, don't use kwargs here.
                self.xformer = FMETransformer(name, pkg, version)
            except FMEException as ex:
                if i == len(resolve) - 1:
                    raise ValueError(
                        f"Could not resolve transformer '{transformer_name}' version {version}"
                    ) from ex
                continue
            self.transformer_name = name
            self.transformer_fpkg = pkg
            break

        self.reset()

    def reset(self):
        """
        Reset all cached state.
        """
        self._last_seen_value = {}
        self._is_required_cache = {}
        self._parsed_values_cache = _ParameterValuesCache(self.xformer)

    def change_version(self, version: Optional[int] = None):
        """
        Change to a different version of the transformer definition.
        This clears state, so serialized parameter values need to be set again
        before their parsed values can be retrieved.

        :param version: Transformer version to load.
            If not specified, then the latest version is loaded.
        """
        if version is None:
            version = -1
        self.xformer = FMETransformer(
            self.transformer_name, self.transformer_fpkg, version
        )
        self.reset()

    def is_required(self, name: str) -> bool:
        """
        :param name: Parameter name.
        :returns: Whether the parameter is required or enabled.
            Returns ``False`` if the parameter is optional or disabled.
        """
        if (cached := self._is_required_cache.get(name)) is None:
            cached = self.xformer.isRequired(name)
            self._is_required_cache[name] = cached
        return cached

    def set(self, name: str, value: Any) -> bool:
        """
        Supply the serialized value of a parameter.
        Its deserialized version can then be retrieved using :meth:`get`.

        :param name: Parameter name to set.
        :param value: Parameter value to set.
            To indicate a null value, use the keyword ``"FME_NULL_VALUE"``.
        """
        self._is_required_cache.clear()  # Any changed parameter value could alter state of any other parameter.
        # "FME_NULL_VALUE" passed as-is to signify FME's null value.
        # Actual None may also be supplied, such as from @Value() and numeric parameters set to null.
        self._last_seen_value[name] = value
        return self.xformer.setParameterValue(name, value)

    def set_all(
        self,
        src: Union[FMEFeature, dict[str, Any]],
        *,
        param_attr_prefix: Optional[str] = "___XF_",
        param_attr_names: Optional[Iterable[str]] = None,
    ) -> bool:
        """
        Supply all serialized parameter values.
        This is the typical way to input parameter values before calling :meth:`get` for deserialized values.

        It is important to set all parameter values before calling :meth:`get`, because
        of dependent parameters that may change or disable the requested parameter.

        Only the parameters that are present in ``src`` and have changed since
        the previous call to this method are used to update the current state.
        Any missing parameters may keep their previous values.

        Transformers that process many features should consider these performance optimizations:

        - Don't rely on attribute prefixing.
          Instead, set ``param_attr_prefix=None`` and
          provide ``param_attr_names`` with a list of all dynamic parameter attribute names.
          Getting attributes by prefix involves an expensive scan of all attribute names present on each feature.
        - If only a small number of parameters change per feature,
          handle them individually using :meth:`set` and :meth:`get`.
        - Avoid unnecessary calls.
          For instance, if parameter B is disabled when parameter A is set to No,
          then check whether parameter A is set to Yes before trying to get parameter B.

        :param src: Source of the serialized transformer parameter values.

            - :class:`fmeobjects.FMEFeature`: Use the attributes on this feature.
            - :class:`dict`: A mapping of parameter names to serialized values.
              This is intended for testing purposes.
        :param param_attr_prefix:
            Prefix for the internal attributes of transformer parameters.
            The default is the prefix used by the FME SDK Guide examples.
            When ``src`` is a feature, all attributes on the feature that start with this prefix
            are collected as transformer parameters.
            Ignored when ``src`` is not a feature. Set to ``None`` to disable prefixing.
        :param param_attr_names:
            Internal attribute names of transformer parameters.
            Only used when ``src`` is a feature.
            If provided, then these attributes are obtained from the feature and
            added to the set of attributes obtained by prefix.
        """
        if isinstance(src, dict):
            self._last_seen_value.update(src)
            self._is_required_cache.clear()
            return self.xformer.setParameterValues(src)

        # The parameter attributes present can vary per feature.
        # Hidden+Disabled parameters have no corresponding attribute.
        # Visible+Disabled parameters raise ValueError.
        #   <b25759: have an <Unused> attribute value: a sentinel value that should not be checked.
        # Empty optional parameters have an attribute with empty string value.
        # FUTURE: FMETransformer can return the full list of parameter names,
        # which we'll cache and reuse instead of scanning all attributes by prefix.
        prefixed_names = ()
        if param_attr_prefix:
            prefixed_names = (
                name
                for name in src.getAllAttributeNames()
                if name.startswith(param_attr_prefix)
            )

        # FUTURE: FMETransformer can return the names of constant parameters,
        # which means we can get their values off the first feature and
        # then skip getting their values on later features.

        # Only set values that have changed since the previous feature
        changes = {}
        for name in itertools.chain(prefixed_names, param_attr_names or ()):
            value = get_attribute(src, name, default=_MISSING)
            if value is _MISSING:
                continue
            if self._last_seen_value.get(name, object) != value:
                self._last_seen_value[name] = value
                changes[name] = value
        if changes:
            self._is_required_cache.clear()  # Any changed parameter value could alter state of any other parameter.
            return self.xformer.setParameterValues(changes)
        return True  # No-op: return like setParameterValues({})

    def get(self, name: str, prefix: Optional[str] = "___XF_") -> ParsedParameterType:
        """
        Get a parsed (deserialized) parameter value.
        For convenience, this assumes a prefix for the given parameter name.
        If the parameter value was not set on the transformer,
        then the default value from the transformer definition is returned, if any.

        Do not call this for disabled parameters.
        Instead, check the value of the dependent parameter's dependency parameter,
        and only get the value of the dependent parameter if the dependency is satisfied,
        i.e. the dependent parameter is enabled.

        .. caution::
            Prior to FME 2025.2, multi-choice parameters returned an incorrect value.
            Instead of returning a list where each element is a selection,
            it returns a list containing one element: the unparsed parameter value string.

        .. caution::
            - Table parameters are not supported. Getting the value of a table parameter will raise ValueError.

        :param name: Name of the parameter.
        :param prefix: Prefix of the parameter.
            Specify ``None`` for unprefixed attributes or if the given name
            already includes the prefix.
            The default is the prefix used by the FME SDK Guide examples.
        :raises ValueError:
            - If the parameter is disabled. (FME 2025.2+)
            - When the value of the parameter cannot be deserialized
              according to the type expected by the transformer definition.
        :raises TypeError: When the parameter value type is not supported.
        :raises KeyError: When the parameter name is not recognized.
        :returns: The deserialized parameter value, with special cases:

            - :attr:`ParameterState.NULL` if the parameter value is null.
            - :attr:`ParameterState.NO_OP` if the parameter value is no-op.
            - If the parameter is optional and has no value set (i.e. empty or unspecified),
              then the return value depends on the parameter type:

                - ``None`` for numeric types.
                - ``[]`` for multiple selection types.
                - ``""`` for all other types.
        """
        # It's valid to call get() without set() or set_all().
        # It just returns the default values from the transformer definition.
        if prefix:
            name = prefix + name

        # Get the unparsed value from cache.
        try:
            unparsed_value = self._last_seen_value[name]
        except KeyError:
            # One of the following:
            # a) non-parameter attribute (caller error)
            # b) parameter that was never set (want transformer definition default)
            # c) hidden+disabled parameter that's never been made visible so far.
            # (b) is possible in unit tests that supply a subset of parameter attributes for convenience
            unparsed_value = _MISSING

        # Don't ask FMETransformer to parse sentinel values.
        if (
            isinstance(unparsed_value, str)
            and unparsed_value in _parameter_state_values
        ):
            return ParameterState(unparsed_value)
        # Numeric parameters set to null are represented as true nulls.
        # Any parameter set to get its value from a null-value attribute is also a true null.
        # Represent these using the NULL enum for consistency.
        if unparsed_value is None:
            return ParameterState.NULL

        try:
            if unparsed_value != _MISSING:
                return self._parsed_values_cache.get(name, unparsed_value)
                # Sentinel values impossible here since we handled them above.

            # Value never supplied. Get default from transformer definition.
            # Convert potential sentinel values.
            parsed_value = self.xformer.getParsedParamValue(name)
            if (
                isinstance(parsed_value, str)
                and parsed_value in _parameter_state_values
            ):
                return ParameterState(parsed_value)
            return parsed_value
        except TypeError as ex:
            # Clarify error message for unsupported parameter types.
            if "parameter value does not match a supported type" in str(ex):
                raise TypeError(
                    f"Parsing of '{name}' not yet implemented. It may be table parameter"
                ) from ex
            raise

    def __getitem__(self, key: str) -> ParsedParameterType:
        """
        Like :meth:`get`, but assumes no prefix.
        """
        return self.get(key, prefix=None)

    def __setitem__(self, key: str, value: str):
        """
        Like :meth:`set`, but raises an exception if the value cannot be set.

        :raises ValueError: If the value cannot be set.
        """
        if not self.set(key, value):
            raise ValueError("Could not set item")

    def __delitem__(self, _):
        raise NotImplementedError()
