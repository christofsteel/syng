"""
Imports all sources, so that they add themselves to the
``available_sources`` dictionary.
"""

from typing import Any, get_type_hints

from syng.config import generate_class_from_dict
from syng.sources.files import FilesSource
from syng.sources.s3 import S3Source
from syng.sources.source import Source as Source
from syng.sources.source import SourceConfig
from syng.sources.source import available_sources as available_sources
from syng.sources.youtube import YoutubeSource

__all__ = ["FilesSource", "S3Source", "YoutubeSource"]


def configure_source(config: dict[str, Any], source_type: type[Source]) -> SourceConfig:
    """
    Create a source configuration object for a given dict configuration

    :param configs: Configuration for the source
    :param source_type: Type of the source object for which to create a config object
    :return: An instance of the source config object for the source type
    """
    config_class: type[SourceConfig] = get_type_hints(source_type)["config"]
    config_object: SourceConfig = generate_class_from_dict(config_class, config)
    return config_object


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
        config_object = configure_source(config, source_class)
        if config_object.enabled:
            configured_sources[source] = source_class(config_object)
    return configured_sources
