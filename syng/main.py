"""
Main entry point for the application.

This module contains the main entry point for the application. It parses the
command line arguments and runs the appropriate function based on the arguments.

This module also checks if the client and server modules are available and
imports them if they are. If they are not available, the application will not
run the client or server functions.

Client usage: syng client [-h] [--room ROOM] [--secret SECRET] \
                    [--config-file CONFIG_FILE] [--server SERVER]
Server usage: syng server [-h] [--host HOST] [--port PORT] [--root-folder ROOT_FOLDER] \
                    [--registration-keyfile REGISTRATION_KEYFILE] [--private] [--restricted]
GUI usage: syng gui

The config file for the client should be a yaml file in the following style::

      sources:
        SOURCE1:  
          configuration for SOURCE
        SOURCE2: 
          configuration for SOURCE
        ...
      config:
        server: ...
        room: ...
        preview_duration: ...
        secret: ...
        last_song: ...
        waiting_room_policy: ..
        key: ..
"""

from typing import TYPE_CHECKING
from argparse import ArgumentParser
import os
import multiprocessing
import traceback

import platformdirs

try:
    from syng.gui import run_gui

    GUI_AVAILABLE = True
except ImportError:
    if TYPE_CHECKING:
        from syng.gui import run_gui
    gui_exception = traceback.format_exc()
    GUI_AVAILABLE = False

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
    """
    Main entry point for the application.

    This function parses the command line arguments and runs the appropriate
    function based on the arguments.

    :return: None
    """
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
        # client_parser.add_argument("--key", "-k", default=None)
        client_parser.add_argument("--server", "-S")

    if GUI_AVAILABLE:
        sub_parsers.add_parser("gui")

    if SERVER_AVAILABLE:
        root_path = os.path.join(os.path.dirname(__file__), "static")
        server_parser = sub_parsers.add_parser("server")
        server_parser.add_argument("--host", "-H", default="localhost")
        server_parser.add_argument("--port", "-p", type=int, default=8080)
        server_parser.add_argument("--root-folder", "-r", default=root_path)
        server_parser.add_argument("--registration-keyfile", "-k", default=None)
        server_parser.add_argument("--private", "-P", action="store_true", default=False)
        server_parser.add_argument("--restricted", "-R", action="store_true", default=False)

    args = parser.parse_args()

    if args.action == "client":
        run_client(args)
    elif args.action == "server":
        run_server(args)
    elif args.action == "gui":
        run_gui()
    else:
        try:
            run_gui()
        except NameError:
            print(gui_exception)


if __name__ == "__main__":
    if os.name == "nt":
        multiprocessing.freeze_support()
    main()
