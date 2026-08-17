import os
import sys

__version__ = "1.5.0"


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
