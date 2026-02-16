"""
Imports all sources, so that they add themselves to the
``available_sources`` dictionary.
"""

from typing import get_type_hints

from syng.config import SourceConfig
from syng.sources.files import FilesSource
from syng.sources.s3 import S3Source
from syng.sources.source import Source as Source
from syng.sources.source import available_sources as available_sources
from syng.sources.youtube import YoutubeSource

__all__ = ["FilesSource", "S3Source", "YoutubeSource"]


def available_source_configs() -> dict[str, type[SourceConfig]]:
    return {
        source: get_source_config_type(source_type)
        for source, source_type in available_sources.items()
    }


def get_source_config_type(source_type: type[Source]) -> type[SourceConfig]:
    config_class: type[SourceConfig] = get_type_hints(source_type)["config"]
    return config_class


def configure_sources(configs: dict[str, SourceConfig]) -> dict[str, Source]:
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
        config_object = config
        if config_object.enabled:
            configured_sources[source] = source_class(config_object)
    return configured_sources
