# fmetools changes

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
