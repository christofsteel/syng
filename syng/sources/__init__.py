"""
Imports all sources, so that they add themselves to the
``available_sources`` dictionary.
"""

# pylint: disable=useless-import-alias

from typing import Any

from .source import available_sources as available_sources
from .source import Source as Source
from .youtube import YoutubeSource  # noqa: F401
from .s3 import S3Source  # noqa: F401
from .files import FilesSource  # noqa: F401


def configure_sources(configs: dict[str, Any]) -> dict[str, Source]:
    """
    Create a Source object for each entry in the given configs dictionary.

    :param configs: Configurations for the sources
    :type configs: dict[str, Any]
    :return: A dictionary, mapping the name of the source to the
      source object
    :rtype: dict[str, Source]
    """
    configured_sources = {}
    for source, config in configs.items():
        if source in available_sources:
            if "enabled" in config and config["enabled"]:
                configured_sources[source] = available_sources[source](config)
    return configured_sources
