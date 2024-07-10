from typing import TYPE_CHECKING
from argparse import ArgumentParser
import os

import platformdirs

from syng.gui import run_gui

try:
    from .client import run_client

    CLIENT_AVAILABLE = True
except ImportError:
    if TYPE_CHECKING:
        from .client import run_client

    CLIENT_AVAILABLE = False

try:
    from .server import run_server

    SERVER_AVAILABLE = True
except ImportError:
    if TYPE_CHECKING:
        from .server import run_server

    SERVER_AVAILABLE = False


def main() -> None:
    parser: ArgumentParser = ArgumentParser()
    sub_parsers = parser.add_subparsers(dest="action")

    if CLIENT_AVAILABLE:
        client_parser = sub_parsers.add_parser("client")

        client_parser.add_argument("--room", "-r")
        client_parser.add_argument("--secret", "-s")
        client_parser.add_argument(
            "--config-file",
            "-C",
            default=f"{os.path.join(platformdirs.user_config_dir('syng'), 'config.yaml')}",
        )
        client_parser.add_argument("--key", "-k", default=None)
        client_parser.add_argument("--server", "-S")

        sub_parsers.add_parser("gui")

    if SERVER_AVAILABLE:
        root_path = os.path.join(os.path.dirname(__file__), "static")
        server_parser = sub_parsers.add_parser("server")
        server_parser.add_argument("--host", "-H", default="localhost")
        server_parser.add_argument("--port", "-p", type=int, default=8080)
        server_parser.add_argument("--root-folder", "-r", default=root_path)
        server_parser.add_argument("--registration-keyfile", "-k", default=None)

    args = parser.parse_args()

    if args.action == "client":
        run_client(args)
    elif args.action == "server":
        run_server(args)
    else:
        run_gui()


if __name__ == "__main__":
    main()
