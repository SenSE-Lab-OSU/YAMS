import os
import sys

from yams import __version__  # noqa: F401  (re-exported for callers)

# YAMS 2.x is a thin MSense-only front-end over PLASMA. These are the identity
# knobs it hands to PLASMA's app_context — kept here so the launcher, the CLI
# shims and the PyInstaller specs all agree.
APP_NAME = "YAMS"
JOURNAL_STREAM = "YAMS"
DATA_DIR_NAME = "yams-data"
CONFIG_FILENAME = "yams_device_config.json"
GYRO_BIAS_FILENAME = "yams_gyro_bias.json"


def resource_path(*parts):
    """Absolute path to a bundled resource, in-place or inside a frozen build.

    PyInstaller unpacks `datas` under sys._MEIPASS, so paths relative to this
    source file are wrong in a frozen app. Returns the path whether or not it
    exists — callers that can degrade should check.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return os.path.join(base, "yams", "resources", *parts)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", *parts)


def favicon_path():
    """Browser-tab icon for the Gradio app, or None if it isn't bundled."""
    path = resource_path("icons", "yams_favicon.png")
    return path if os.path.exists(path) else None
