"""
Imports all sources, so that they add themselves to the
``available_sources`` dictionary.
"""

# pylint: disable=useless-import-alias

from typing import Any

from syng.sources.files import FilesSource  # noqa: F401
from syng.sources.s3 import S3Source  # noqa: F401
from syng.sources.source import Source as Source
from syng.sources.source import available_sources as available_sources
from syng.sources.youtube import YoutubeSource  # noqa: F401

__all__ = ["FilesSource", "S3Source", "YoutubeSource"]


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
        source_class = available_sources.get(source, None)
        if source_class is None:
            raise RuntimeError(f"Could not find source '{source}'")
        config_object = source_class.generate_config_from_dict(config)
        if config_object.enabled:
            configured_sources[source] = source_class(config_object)
    return configured_sources
