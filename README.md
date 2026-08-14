# fmetools: helpers for FME Python

_fmetools_ is a Python library that streamlines plugin development for [Safe Software's FME][fme].
Developers should use fmetools as a foundation to create plugins such as transformers.
It's part of the recommended toolchain for developing FME Packages to share on [FME Hub][hub].

fmetools is built on top of the [Python `fmeobjects` API][fmeobjects] that's included with FME,
and requires an FME installation with Python 3.8 or newer.

## Getting started

The best way to get started with fmetools is through the tutorials in the [FME Packages SDK Guide][fpkg-sdk].
The [Hello World package tutorial][hello world] guides you through creating a simple FME Package that uses fmetools.

The fmetools API reference is available at https://docs.safe.com/fme/html/fmetools/.

[fme]: https://safe.com
[hub]: https://hub.safe.com
[fpkg-sdk]: https://docs.safe.com/fme/html/fpkg-sdk/
[hello world]: https://docs.safe.com/fme/html/fpkg-sdk/hello-world-package/
[vendorize]: https://pypi.org/project/vendorize/
[fmeobjects]: https://docs.safe.com/fme/html/fmepython/index.html


## Installation

fmetools is distributed as a wheel on [PyPI](https://pypi.org/project/fmetools/),
but it should _not_ be installed with `pip install`.
Instead, developers include a copy of fmetools with their FME Package.
This process is called vendorizing, and can be done using the [vendorize][vendorize] tool on PyPI.
The [Hello World package tutorial][hello world] covers this topic.

FME does not include fmetools, so packages that use it must include it themselves.

## For maintainers of fmetools

1. Install dependencies with `uv sync`.
2. Set up access to fmeobjects using `uv run fme-packager config-env`.
3. Run tests using `uv run pytest`. `tox.ini` contains more specific invocations.
4. Build wheel with `uv build`.
5. Build docs with `uv run sphinx-build docs _build`.
