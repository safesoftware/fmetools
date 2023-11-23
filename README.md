# fmetools: helpers for FME Python

_fmetools_ is a Python library that streamlines plugin development for [Safe Software's FME][fme].
Developers should use fmetools as a foundation to create plugins such as transformers.
It's part of the recommended toolchain for developing FME Packages to share on [FME Hub][hub].

fmetools is built on top of the [Python `fmeobjects` API][fmeobjects] that's included with FME,
and requires an FME installation with Python 3.7 or newer.

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

1. Start with a clean environment
2. Install dev requirements using `pip install -r requirements.txt`
3. Do a dev install using `pip install --editable .`
4. Run tests using `pytest`
5. Build wheel using `python -m build --wheel`
6. To build docs: `sphinx-build -M html docs docs/_build`
