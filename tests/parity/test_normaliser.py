"""The Python parity runner replaces the run's directories the way the Go program does."""

from __future__ import annotations

from parity.run_python import Normaliser


def test_normaliser_replaces_tmp_escaped_in_configuration_text():
    n = Normaliser(tmp="C:\\Temp\\xcl-parity-1", fixture="D:\\fixtures\\plugin_entities")

    text = n.text('log = "C:\\\\Temp\\\\xcl-parity-1/recording.log"')

    assert text == 'log = "<tmp>/recording.log"'


def test_normaliser_replaces_fixture_escaped_in_configuration_text():
    n = Normaliser(tmp="C:\\Temp\\xcl-parity-1", fixture="D:\\fixtures\\plugin_entities")

    text = n.text('source = "D:\\\\fixtures\\\\plugin_entities\\\\main.xcl"')

    assert text == 'source = "<fixture>\\\\main.xcl"'


def test_normaliser_replaces_tmp_as_written():
    n = Normaliser(tmp="C:\\Temp\\xcl-parity-1", fixture="D:\\fixtures\\plugin_entities")

    text = n.text("C:\\Temp\\xcl-parity-1\\state")

    assert text == "<tmp>\\state"
