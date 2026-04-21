"""CLI for bilark - Bilibili archiving made simple"""

from pathlib import Path
from colorama import Style, Fore
import sys
import threading
import webbrowser
from .errors import _err_msg, ArchiveNotFoundException
from .channel import Channel, DownloadConfig
from .viewer import viewer

HELP = """bilark [options]

  Bilibili archiving made simple.

Options:
  new [name] [url/uid]     Creates new archive with name and channel url or UID
  refresh [name] [args?]   Refreshes/downloads archive with optional config
  view [name?]             Launches offline archive viewer website
  report [name]            Provides a report on the most interesting changes

Example:
  $ bilark new vtuber https://space.bilibili.com/12345678/video
  $ bilark new vtuber 12345678
  $ bilark refresh vtuber
  $ bilark view vtuber"""


def _cli():
    args = sys.argv[1:]

    if len(args) == 0:
        print(HELP, file=sys.stderr)
        _err_msg("\nError: No arguments provided")
        sys.exit(1)

    if args[0] in ["help", "--help", "-h"]:
        print(HELP)

    elif args[0] in ["-v", "-ver", "--version", "--v"]:
        print("1.0.0")

    elif args[0] == "new":
        if len(args) == 2 and args[1] == "--help":
            print(HELP)
            sys.exit(0)
        if len(args) < 3:
            _err_msg("Please provide an archive name and the channel url or UID")
            sys.exit(1)
        Channel.new(Path(args[1]), args[2])

    elif args[0] == "refresh":
        if len(args) == 2 and args[1] == "--help":
            print("""bilark refresh [name] [args?]

  Refreshes/downloads archive with optional configuration.

Arguments:
  --videos=[max]        Maximum recent videos to download
  --skip-metadata       Skips downloading metadata
  --skip-download       Skips downloading content
  --format=[str]        Downloads using custom yt-dlp format

Example:
  $ bilark refresh vtuber
  $ bilark refresh vtuber --videos=10
  $ bilark refresh vtuber --skip-download""")
            sys.exit(0)

        if len(args) < 2:
            _err_msg("Please provide the archive name")
            sys.exit(1)

        config = DownloadConfig()
        if len(args) > 2:
            def parse_value(arg): return arg.split("=")[1]
            def parse_int(arg):
                v = parse_value(arg)
                try: return int(v)
                except:
                    _err_msg(f"The value '{v}' isn't a valid number")
                    sys.exit(1)

            for config_arg in args[2:]:
                if config_arg.startswith("--videos="):
                    config.max_videos = parse_int(config_arg)
                elif config_arg == "--skip-metadata":
                    config.skip_metadata = True
                elif config_arg == "--skip-download":
                    config.skip_download = True
                elif config_arg.startswith("--format="):
                    config.format = parse_value(config_arg)
                else:
                    _err_msg(f"Unknown configuration '{config_arg}'")
                    sys.exit(1)

        config.submit()

        try:
            channel = Channel.load(args[1])
            if config.skip_metadata:
                print("Skipping metadata download..")
            else:
                channel.metadata()
                channel.commit()
            if config.skip_download:
                print("Skipping video download..")
            else:
                channel.download(config)
            channel.reporter.print()
        except ArchiveNotFoundException:
            _err_archive_not_found()

    elif args[0] == "view":
        if len(args) == 2 and args[1] == "--help":
            print("""bilark view [name?] [args?]

  Launches offline archive viewer website.

Arguments:
  --host=[str]  Custom host address
  --port=[int]  Custom port (default: 7667)

Example:
  $ bilark view vtuber
  $ bilark view vtuber --port=8080""")
            sys.exit(0)

        host = None
        port = 7667

        for config_arg in args[2:]:
            if config_arg.startswith("--host="):
                host = config_arg[7:]
            elif config_arg.startswith("--port="):
                try:
                    port = int(config_arg[7:])
                except:
                    _err_msg(f"Invalid port number '{config_arg[7:]}'")
                    sys.exit(1)

        def launch():
            app = viewer()
            threading.Thread(target=lambda: app.run(host=host, port=port)).run()

        if len(args) > 1 and not args[1].startswith("--"):
            channel = args[1]
            if not Path(channel).exists():
                _err_archive_not_found()
            print(f"Starting viewer for {channel}..")
            webbrowser.open(f"http://127.0.0.1:{port}/channel/{channel}/videos")
            launch()
        else:
            print("Starting viewer..")
            webbrowser.open(f"http://127.0.0.1:{port}/")
            launch()

    elif args[0] == "report":
        if len(args) < 2:
            _err_msg("Please provide the archive name")
            sys.exit(1)
        channel = Channel.load(Path(args[1]))
        channel.reporter.interesting_changes()

    else:
        print(HELP, file=sys.stderr)
        _err_msg(f"\nError: Unknown command '{args[0]}'", True)
        sys.exit(1)


def _err_archive_not_found():
    _err_msg("Archive doesn't exist, please make sure you typed its name correctly!")
    sys.exit(1)
