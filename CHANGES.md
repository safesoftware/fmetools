# fmetools changes

## 0.10.3

* Updated docstring references to `fmetools._deprecated.FMEBaseTransformer.*` to link to new `fme.BaseTransformer` documentation.


## 0.10.2

* FMERequestsSession: Fix use of Windows Certificate Store in
  FME 2024.1.2+ and Requests 2.32.3+.

## 0.10.1

* Use `fme.BaseTransformer` if it exists.
* Deprecate `fmetools.plugins.FMEBaseTransformer`.

## 0.10.0

* Fix support for Python 3.8 and require Python 3.8+.

## 0.9.3

* Update docstrings for FMEEnhancedTransformer and FMEBaseTransformer.

## 0.9.2

* In `fmetools.scripted_selection.ContainerContentResponse`,
  omit `CONTINUE` key if there's no pagination info.

## 0.9.1

* Allow ScriptedSelectionCallback subclasses to omit constructor.

## 0.9.0

* Add support for multiple input tags. Requires FME 2024.0+.

## 0.8.0

* Add support for multiple output tags. Requires FME 2024.0+.

## 0.7.4

* Update doc for `fmetools.paramparsing` to note FME 2024 requirement
  when running under FME Flow.
* Add Scripted Selection API

## 0.7.3

* Add links to HTML docs.

## 0.7.2

* Relax FME version requirements from 0.7.0 release.

## 0.7.1

* Fix type annotations when using Python 3.8 and earlier.

## 0.7.0

* Add HTML docs and expanded existing docstrings.
* Clarify which components are considered part of the public API.
* Add type annotations.
* `fmetools.plugins.FMEEnhancedTransformer`: Support Bulk Mode by default.

## 0.6.0

* Rename `fmetools.plugins.FMETransformer` to `FMEBaseTransformer`
  to avoid potential confusion with `fmeobjects.FMETransformer`.
  Instantiating `fmetools.plugins.FMETransformer` now emits a warning,
  and will be removed in a future release.
* `fmetools.paramparsing.TransformerParameterParser`: Support FME >= b23264.

## 0.5.1

* Add `fmetools.paramparsing.TransformerParameterParser`: a class for parsing
  internal attribute values from transformer parameters. Requires FME 2023.
* Require Python 3.7+.

## 0.4.4

* Fixed error when parsing custom proxy URLs starting with 'http'

## 0.4.3

* Support new GUI types `CHECKBOX` and `CHOICE`.

## 0.4.2

* Prepare for PyPI release.

## 0.4.0

* Support new GUI types `ACTIVECHOICE_LOOKUP` and `NAMED_CONNECTION`.
* Int and float GUI types: parse empty string to None instead of raising ValueError.

## 0.3.1

* Fix FMESession leak in `parsers.parse_def_line()`.

## 0.3.0

* Add `guiparams` module, for parsing GUI parameter values.
  This initial implementation supports just a small subset of GUI types.

## 0.2.0

* Remove `FMEEnhancedTransformer.keyword` and replace its usages with `FMETransformer.factory_name`.
* Use relative imports, to support copy-paste vendorization.

## 0.1.4

* Add `hasSupportFor()` to `plugins.FMESimplifiedReader` to allow for reader bulk mode support.

## 0.1.3

* Add `webservices.set_session_auth_from_named_connection()` to honour SSL verification settings on Named Connections.

## 0.1.2

* Add `has_support_for()` to `plugins.FMETransformer` to enable transformer bulk mode support.

## 0.1.1

* Maintain Python 2.7 support.

## 0.1.0

* Respect web connection token placement settings.

## 0.0.2

* Added localization utilities.
* Updated logging infrastructure.

## 0.0.1

* Initial packaging of utility functions.
