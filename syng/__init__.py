from importlib.metadata import version, PackageNotFoundError
from packaging.version import Version

try:
    __version__ = version("syng")
    SYNG_VERSION = Version(__version__).release
except PackageNotFoundError:
    __version__ = "unknown"
    SYNG_VERSION = (0, 0, 0)


SYNG_PROTOCOL_VERSION = (2, 2, 0)
