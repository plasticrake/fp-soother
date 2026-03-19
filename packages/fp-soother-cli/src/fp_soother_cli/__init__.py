from importlib.metadata import version

from .cli import main

__all__ = ["main"]

__version__ = version("fp-soother-cli")
