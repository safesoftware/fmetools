# fmetools: helpers for FME Python

_fmetools_ is a Python library containing functions and classes for use with
Safe Software's FME. It streamlines the development of Python-based
formats and transformers that can be shared as FME Packages on FME Hub.

This library is built on top of the
[Python `fmeobjects` API](https://docs.safe.com/fme/html/fmepython/index.html)
that's included with FME.

## Installation

Developers of FME Packages use _fmetools_ by including a private copy it
in their FME Package. This process is called vendorization, and can be done
using the [vendorize](https://pypi.org/project/vendorize/) tool on PyPI.

_fmetools_ is distributed as a wheel, but it should _not_ be installed
with `pip install`.


## For maintainers of fmetools

1. Start with a clean environment
2. Install dev requirements using `pip install -r requirements.txt`
3. Do a dev install using `pip install --editable .`
4. Run tests using `pytest`
5. Build wheel using `python -m build --wheel`
