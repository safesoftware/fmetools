# coding: utf-8

import fme
from fmeobjects import FMEFeature

from fmetools.plugins import (
    FMESimplifiedReader,
    FMEEnhancedTransformer,
    FMESimplifiedWriter,
)

from unittest.mock import patch


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


def test_enhanced_transformer():
    with FMEEnhancedTransformer() as xformer:
        assert xformer.factory_name == "FMEEnhancedTransformer"
        assert xformer.log.name == xformer.factory_name
        xformer.input(FMEFeature())

        with patch.object(xformer, "pyoutput") as pyoutput:
            xformer.reject_feature(FMEFeature(), "code", "message")
            feature = pyoutput.call_args.args[0]
            assert feature.getAttribute("fme_rejection_code") == "code"
            assert feature.getAttribute("fme_rejection_message") == "message"

        # Redundant closes should be safe.
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
