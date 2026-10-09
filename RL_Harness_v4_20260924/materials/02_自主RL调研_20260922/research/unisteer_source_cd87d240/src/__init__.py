"""UniSteer training and online adaptation package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("unisteer")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
