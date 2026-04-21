"""Exceptions and error functions"""

from colorama import Style, Fore
import sys


class ArchiveNotFoundException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class VideoNotFoundException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class NoteNotFoundException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class TimestampException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


def _err_msg(msg: str, report_msg: bool = False):
    msg = (
        msg
        if not report_msg
        else f"{msg}\nPlease file a bug report if you think this is a problem with Bilark!"
    )
    print(Fore.RED + Style.BRIGHT + msg + Style.NORMAL + Fore.RESET, file=sys.stderr)
