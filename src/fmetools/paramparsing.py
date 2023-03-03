"""
This module provides tools for working with transformer parameters.
This module can only be imported in FME 2023 or newer.
"""
from typing import Any, Iterable, Optional, Union

from fmetools.features import get_attributes, get_attributes_with_prefix

try:
    from fmeobjects import FMEException, FMEFeature, FMETransformer
except ModuleNotFoundError as e:
    raise ModuleNotFoundError(str(e) + " (introduced in FME 2023 b23224)")


class TransformerParameterParser:
    """
    Helper for getting parsed transformer parameter values.

    All parameters of Python transformers are set as attributes on input features.
    By convention, these attributes are given a prefix to give it a namespace and
    signify that they are internal attributes.
    The values of these attributes are string serializations.

    This class works by loading a transformer definition from FME,
    and using its parameter definitions to parse serialized parameter values.

    A typical workflow with this class involves:

    1. Instantiate this class as an instance member on the class that implements
       the transformer.
    2. When the transformer receives its first input feature:
       - If the caller is aware that it needs a particular transformer version,
         it may call TransformerParameters.change_version().
       - TransformerParameters.set_all() is called to provide all initial
         serialized parameter values from the input feature.
       - TransformerParameters.get() is called to get the deserialized values
         for the parameters of interest.
         If these parameter values don't change between features,
         the caller caches them to avoid unnecessary re-parsing of values.
    3. For subsequent input features, TransformerParameters.set_all()
       and TransformerParameters.get() are called as necessary to handle the
       values of parameters that change between features, if any.
    """

    xformer: FMETransformer
    transformer_name: str
    transformer_fpkg: Optional[str]

    def __init__(
        self,
        transformer_name: str,
        version: Optional[int] = None,
    ):
        """
        :param transformer_name: Fully-qualified name of the transformer.
        :param version: Transformer version to load.
            If not provided, then the latest version is loaded.
        :raises ValueError: If FME cannot find the specified transformer.
        """
        # If the given name is foo.bar.baz, then first try using foo.bar as
        # the fmePackageName argument, for better performance.
        # Fully-qualified package name is still required.
        # FMETransformer will also take the fully-qualified name without
        # the fmePackageName argument, but it's slower.
        resolve = [(transformer_name, None)]
        name_parts = transformer_name.split(".", maxsplit=2)
        if len(name_parts) == 3:
            resolve.insert(0, (transformer_name, ".".join(name_parts[:2])))

        for name, pkg in resolve:
            try:
                self.xformer = FMETransformer(
                    name, fmePackageName=pkg, transformerVersion=version
                )
                self.transformer_name = name
                self.transformer_fpkg = pkg
            except FMEException:
                continue
            if self.xformer:
                break
        try:
            self.xformer
        except AttributeError as e:
            raise ValueError(f"Could not resolve {transformer_name}") from e

    def change_version(self, version: Optional[int] = None):
        """
        Change to a different version of the transformer definition.
        This clears state, so serialized parameter values need to be set again
        before their parsed values can be retrieved.

        :param version: Transformer version to load.
            If not provided, then the latest version is loaded.
        """
        self.xformer = FMETransformer(
            self.transformer_name,
            fmePackageName=self.transformer_fpkg,
            transformerVersion=version,
        )

    def is_required(self, name) -> bool:
        """
        :param name: Parameter name.
        :returns: True if the parameter is required according to the
            transformer definition.
            False if the parameter is disabled, which may occur
            based on the values of other parameters.
        """
        return self.xformer.isRequired(name)

    def set(self, name, value) -> bool:
        """
        Supply the serialized value of a parameter.
        Its deserialized version can then be retrieved using get().

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
        This is the typical way to input parameter values before calling get()
        to obtain their deserialized values.

        It is important to set all parameter values before calling get(), because
        of dependent parameters that may change or disable the requested parameter.

        :param src: Source of the serialized transformer parameter values.
            If FMEFeature, then these are all the attributes on the feature
            that start with the param_attr_prefix provided in the constructor.
            If dict, then this is a mapping of parameter names to serialized values.
        :param param_attr_prefix:
            Prefix for the internal attributes of transformer parameters.
            The default is the prefix used by the FME SDK Guide examples.
            Only used when src is a feature.
        :param param_attr_names:
            Internal attribute names of transformer parameters.
            Only used when src is a feature. If provided, then these attributes
            are obtained from the feature and added to the set of attributes
            obtained by prefix.
        """
        if isinstance(src, FMEFeature):
            attrs = get_attributes_with_prefix(src, param_attr_prefix)
            if param_attr_names:
                attrs.update(get_attributes(src, param_attr_names))
            src = attrs
        return self.xformer.setParameterValues(src)

    def get(self, name) -> Any:
        """
        Get a parsed (deserialized) parameter value.
        If the parameter value was not set on the transformer,
        then the default value is returned, if any.

        :raises ValueError: When the value of the parameter cannot be deserialized
            according to the type expected by the transformer definition.
        :raises TypeError: When the parameter value type is not supported.
        :raises KeyError: When the parameter name is not recognized.
        """
        return self.xformer.getParsedParamValue(name)

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        if not self.set(key, value):
            raise ValueError("Could not set item")

    def __delitem__(self, _):
        raise NotImplementedError()
