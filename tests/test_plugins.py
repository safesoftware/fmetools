import fme
from fmeobjects import FMEFeature

from fmetools.plugins import (
    FMESimplifiedReader,
    FMEEnhancedTransformer,
    FMESimplifiedWriter,
)

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch  # PY2 backport library


class MockReader(FMESimplifiedReader):
    def read(self):
        return None

    def readSchema(self):
        return None


def test_reader():
    """Sanity check for reader instantiation and various lifecycle calls."""
    with patch("pluginbuilder.FMEMappingFile") as mf, MockReader("T", "K", mf) as rdr:
        rdr.open("foobar", [])
        rdr.setConstraints(FMEFeature())
        rdr.open("foobar", [])
        rdr.readGenerator()
        rdr.readSchemaGenerator()
        rdr.abort()
        rdr.abort()
        rdr.close()
        rdr.close()


class MockWriter(FMESimplifiedWriter):
    def multiFileWriter(self):
        return False

    def write(self, feature):
        pass


def test_writer():
    """Sanity check for writer instantiation and various lifecycle calls."""
    with patch("pluginbuilder.FMEMappingFile") as mf, MockWriter("T", "K", mf) as wtr:
        wtr.open("foobar", [])
        wtr.write(FMEFeature())
        wtr.abort()
        wtr.abort()
        wtr.close()
        wtr.close()


def test_enhanced_transformer(monkeypatch):
    with FMEEnhancedTransformer() as xformer:
        assert xformer.keyword == "Transformer"
        xformer.input(FMEFeature())

        def reject_assert(feature):
            assert feature.getAttribute("fme_rejection_code") == "code"
            assert feature.getAttribute("fme_rejection_message") == "message"

        monkeypatch.setattr(xformer, "pyoutput", reject_assert)
        xformer.reject_feature(FMEFeature(), "code", "message")

        xformer.close()
        xformer.close()


def test_constructors_handle_missing_macrovalues(monkeypatch):
    """
    Classes with constructors that access `fme.macroValues` need to handle the case
    where `macroValues` is undefined on older FME.
    """
    monkeypatch.delattr(fme, "macroValues", raising=False)
    with patch("pluginbuilder.FMEMappingFile") as mf:
        MockReader("T", "K", mf)
        MockWriter("T", "K", mf)
    FMEEnhancedTransformer()
