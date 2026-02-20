"""Syng: All-in-one Karaoke Software.

This module sets the version number from the packaging, as well as a prococol version for
communication between server and client.

"""

from importlib.metadata import PackageNotFoundError, version

from packaging.version import Version

try:
    __version__ = version("syng")
    SYNG_VERSION = Version(__version__).release
except PackageNotFoundError:
    __version__ = "unknown"
    SYNG_VERSION = (0, 0, 0)


SYNG_PROTOCOL_VERSION = (2, 2, 0)
