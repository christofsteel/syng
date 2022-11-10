from minio import Minio
from time import perf_counter

from .source import Source, async_in_thread, available_sources
from ..result import Result


class S3Source(Source):
    def __init__(self, config):
        super().__init__()
        self.minio = Minio(
            config["s3_endpoint"],
            access_key=config["access_key"],
            secret_key=config["secret_key"],
        )
        self.bucket = config["bucket"]

    def init_server(self):
        print("Start indexing")
        start = perf_counter()
        self.index = list(self.minio.list_objects("bucket"))
        stop = perf_counter()
        print(f"Took {stop - start:0.4f} seconds")

    @async_in_thread
    def search(self, query: str) -> list[Result]:
        pass

    async def build_index():
        pass


available_sources["s3"] = S3Source
