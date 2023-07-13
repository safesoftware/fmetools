# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "fmetools"
copyright = "2023, Safe Software Inc."
author = "Safe Software Inc."

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["sphinx.ext.autodoc", "sphinx.ext.autosummary", "sphinx.ext.intersphinx"]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "fmeobjects": ("https://docs.safe.com/fme/html/fmepython/", None),
    "requests": ("https://requests.readthedocs.io/en/latest/", None),
}

autodoc_default_options = {
    "special-members": "__init__",
    "show-inheritance": True,
}
autodoc_mock_imports = ["fme", "fmeobjects", "fmewebservices", "pluginbuilder"]
