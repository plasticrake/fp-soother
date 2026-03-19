"""fp-soother-web: a local web UI for controlling a paired Soother."""

from importlib.metadata import version

from .app import create_app

__all__ = ["create_app"]

__version__ = version("fp-soother-web")
