#!/usr/bin/env python3
"""Put a model server on Google Cloud or Azure for the pepa workers. No arguments opens the menu;
any subcommand runs directly.
"""
import argparse
import io
import sys

from cli import deploy, install, menu, servers, ui
from settings import COMMAND, HOSTS, SERVERS


def main():
    parser = argparse.ArgumentParser(prog=COMMAND, description="Put a model server on Google Cloud or Azure for the pepa workers.")
    parser.add_argument("--no-input", action="store_true", help="Never ask a question: each one takes its default answer")
    sub = parser.add_subparsers(dest="command")

    d = sub.add_parser("deploy", help="Put a model server on Google Cloud or Azure")
    d.add_argument("--host", choices=list(HOSTS), help="Where the server runs")
    d.add_argument("--server", choices=list(SERVERS), help="Which server: small runs on CPU, large on a GPU")

    sub.add_parser("list", help="List the deployed servers")

    r = sub.add_parser("remove", help="Delete a deployed server")
    r.add_argument("name", nargs="?", help="The server's name, as list shows it")

    sub.add_parser("install", help="Check which hosts are ready")

    args = parser.parse_args()
    if args.no_input:
        sys.stdin = io.StringIO()
    if args.command is None:
        return menu.main()
    if args.command == "deploy":
        return deploy.run(host_name=args.host, server_name=args.server)
    if args.command == "list":
        return servers.list_servers()
    if args.command == "remove":
        return servers.remove_server(args.name)
    if args.command == "install":
        return install.run()


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
        sys.exit(0)
    except SystemExit as e:
        if isinstance(e.code, str):
            ui.error(e.code)
            sys.exit(1)
        raise
