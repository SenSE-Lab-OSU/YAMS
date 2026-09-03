"""YAMS 2.x is a thin front-end over PLASMA — these check the wiring, not the
acquisition/analysis logic (that lives in PLASMA's own test suite)."""
import pytest

pytest.importorskip("plasma", reason="install PLASMA: pip install -e ../PLASMA")


def test_version():
    import yams

    assert yams.__version__.split(".")[0] == "2"


def test_configure_rebrands_to_yams():
    from plasma.app_context import app_context
    from yams.__main__ import _configure

    _configure()
    ctx = app_context()
    assert ctx.app_name == "YAMS"
    assert ctx.journal_stream == "YAMS"
    assert ctx.config_path.endswith("yams_device_config.json")
    assert ctx.data_dir.endswith("yams-data")


def test_build_assembles_the_app(monkeypatch, tmp_path):
    monkeypatch.setenv("PLASMA_HOME", str(tmp_path))
    from plasma import app_context
    from plasma.config import device_config

    app_context.reset()
    from yams.__main__ import build

    demo = build()
    assert demo.__class__.__name__ == "Blocks"
    # YAMS is single-sensor: only the MSense plugin is enabled
    assert device_config._active == ["MSense Wristbands"]


def test_cli_shims_import():
    import yams.data_extraction as de
    import yams.msense_yams_sync as sync

    assert callable(de.main)
    assert callable(sync.main)
