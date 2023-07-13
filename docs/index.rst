fmetools documentation
======================

This is the API reference documentation for *fmetools*.

fmetools is a Python library that streamlines plugin development for `Safe Software's FME <fme_>`_.
Developers should use fmetools as a foundation to create plugins such as transformers.
It's part of the recommended toolchain for developing FME Packages to share on `FME Hub <hub_>`_.

fmetools is built on top of the `Python fmeobjects API <fmeobjects_>`_ that's included with FME,
and requires an FME installation with Python 3.7 or newer.


Getting started
---------------

The best way to get started with fmetools is through the tutorials in the `FME Packages SDK Guide <fpkg-sdk_>`_.
The `Hello World package tutorial <hello world_>`_ guides you through creating a simple FME Package that uses fmetools.

.. _fme: https://safe.com
.. _hub: https://hub.safe.com
.. _fpkg-sdk: https://docs.safe.com/fme/html/fpkg-sdk/
.. _hello world: https://docs.safe.com/fme/html/fpkg-sdk/hello-world-package/
.. _vendorize: https://pypi.org/project/vendorize/
.. _fmeobjects: https://docs.safe.com/fme/html/fmepython/index.html


Installation
------------

fmetools is distributed as a wheel on `PyPI <https://pypi.org/project/fmetools/>`_,
but it should *not* be installed with ``pip install``.
Instead, developers include a copy of fmetools with their FME Package.
This process is called vendorizing, and can be done using the `vendorize`_ tool on PyPI.
The `Hello World package tutorial <hello world_>`_ covers this topic.

FME does not include fmetools, so packages that use it must include it themselves.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   fmetools/index



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
