from .source import Source, available_sources
from .youtube import YoutubeSource
from .s3 import S3Source


def configure_sources(configs: dict, client) -> dict[str, Source]:
    print(available_sources)
    configured_sources = {}
    for source, config in configs.items():
        if source in available_sources:
            configured_sources[source] = available_sources[source](config)
            if client:
                configured_sources[source].init_client()
            else:
                configured_sources[source].init_server()
    return configured_sources
