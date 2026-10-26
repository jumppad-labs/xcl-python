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


def test_pretty_groups_join_indented_lines_to_their_event_line():
    n = Normaliser(tmp="/tmp/run", fixture="/work/fixture")

    groups = n.pretty_groups("3:04PM INFO b second\n  block line\n12:00AM INFO a first duration=1.5ms\n")

    assert groups == ["<time> INFO a first duration=<duration>", "<time> INFO b second\n  block line"]


def test_pretty_groups_strip_colour():
    n = Normaliser(tmp="/tmp/run", fixture="/work/fixture")

    groups = n.pretty_groups("3:04PM \x1b[1;36mINFO\x1b[0m apply start \x1b[2msource\x1b[0m=core\n")

    assert groups == ["<time> INFO apply start source=core"]


def test_pretty_groups_replace_run_paths():
    n = Normaliser(tmp="/tmp/run", fixture="/work/fixture")

    groups = n.pretty_groups('3:04PM INFO create success file=/work/fixture/main.xcl\n  log = "/tmp/run/recording.log"\n')

    assert groups == ['<time> INFO create success file=<fixture>/main.xcl\n  log = "<tmp>/recording.log"']
