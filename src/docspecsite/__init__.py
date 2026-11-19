"""A docs checker and static site generator that renders every version of every doc from git history."""

from importlib.metadata import version

from .errors import DocspecsiteWarning, InternalErrorWarning

__all__ = ["DocspecsiteWarning", "InternalErrorWarning", "__version__"]

__version__ = version("docspecsite")
