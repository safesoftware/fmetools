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

from typing import Any, Iterable, Optional, Union

from fmetools.features import get_attributes, get_attributes_with_prefix

try:
    from fmeobjects import FMEException, FMEFeature, FMETransformer
except ModuleNotFoundError as e:
    raise ModuleNotFoundError(str(e) + " (introduced in FME 2023 b23224)")


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

    This class works by loading a transformer definition from FME,
    passing it serialized parameter values from an input feature or other source,
    and then requesting deserialized values back.
    FME uses the transformer definition to determine how to deserialize the values.

    A typical workflow with this class involves:

    1. Instantiate this class as an instance member of the class that implements
       the transformer.
    2. When the transformer receives its first input feature:

       - If the caller needs a particular transformer version,
         it may call :meth:`change_version`.
       - :meth:`set_all` is called to provide all initial
         serialized parameter values from the input feature.
       - :meth:`get` is called to get the deserialized values
         for the parameters of interest.
         If these parameter values don't change between features,
         the caller caches them to avoid unnecessary work.
    3. For subsequent input features, :meth:`set`
       and :meth:`get` are called as necessary to handle the
       values of parameters that change between features, if any.
    """

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
        self.xformer: FMETransformer
        self.transformer_name: str
        self.transformer_fpkg: Optional[str]

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
                    raise ValueError(f"Could not resolve {transformer_name}") from ex
                continue
            self.transformer_name = name
            self.transformer_fpkg = pkg
            break

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

    def is_required(self, name: str) -> bool:
        """
        :param name: Parameter name.
        :returns: Whether the parameter is required according to the
            transformer definition.
            If the parameter is disabled, this returns ``False``.
        """
        return self.xformer.isRequired(name)

    def set(self, name: str, value: Any) -> bool:
        """
        Supply the serialized value of a parameter.
        Its deserialized version can then be retrieved using :meth:`get`.

        :param name: Parameter name to set.
        :param value: Parameter value to set.
        """
        return self.xformer.setParameterValue(name, value)

    def set_all(
        self,
        src: Union[FMEFeature, dict[str, Any]],
        *,
        param_attr_prefix: str = "___XF_",
        param_attr_names: Optional[Iterable[str]] = None,
    ) -> bool:
        """
        Supply all serialized parameter values.
        This is the typical way to input parameter values before calling :meth:`get`
        to obtain their deserialized values.

        It is important to set all parameter values before calling :meth:`get`, because
        of dependent parameters that may change or disable the requested parameter.

        :param src: Source of the serialized transformer parameter values.

            - :class:`fmeobjects.FMEFeature`: Use the attributes on this feature.
            - :class:`dict`: A mapping of parameter names to serialized values.
        :param param_attr_prefix:
            Prefix for the internal attributes of transformer parameters.
            The default is the prefix used by the FME SDK Guide examples.
            Only used when ``src`` is a feature.
        :param param_attr_names:
            Internal attribute names of transformer parameters.
            Only used when ``src`` is a feature.
            If provided, then these attributes are obtained from the feature and
            added to the set of attributes obtained by prefix.
        """
        if isinstance(src, FMEFeature):
            attrs = get_attributes_with_prefix(src, param_attr_prefix)
            if param_attr_names:
                attrs.update(get_attributes(src, param_attr_names))
            src = attrs
        return self.xformer.setParameterValues(src)

    def get(self, name: str, prefix: Optional[str] = "___XF_") -> Any:
        """
        Get a parsed (deserialized) parameter value.
        For convenience, this assumes a prefix for the given parameter name.
        If the parameter value was not set on the transformer,
        then the default value is returned, if any.

        :param name: Name of the parameter.
        :param prefix: Prefix of the parameter.
            Specify ``None`` for unprefixed attributes or if the given name
            already includes the prefix.
            The default is the prefix used by the FME SDK Guide examples.
        :raises ValueError: When the value of the parameter cannot be deserialized
            according to the type expected by the transformer definition.
        :raises TypeError: When the parameter value type is not supported.
        :raises KeyError: When the parameter name is not recognized.
        """
        if prefix:
            name = prefix + name
        return self.xformer.getParsedParamValue(name)

    def __getitem__(self, key):
        return self.get(key, prefix=None)

    def __setitem__(self, key, value):
        if not self.set(key, value):
            raise ValueError("Could not set item")

    def __delitem__(self, _):
        raise NotImplementedError()
