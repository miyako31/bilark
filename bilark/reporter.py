"""Channel reporting system (Bilibili edition)"""

from colorama import Fore, Style
import datetime
from .video import Video, Element
from .utils import _truncate_text
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .channel import Channel


class Reporter:
    channel: "Channel"
    added: list
    deleted: list
    updated: list

    def __init__(self, channel) -> None:
        self.channel = channel
        self.added = []
        self.deleted = []
        self.updated = []

    def print(self):
        """Prints coloured report to STDOUT"""
        print(f"Report for {self.channel}:")

        for kind, element in self.updated:
            colour = Fore.CYAN if kind in ["title", "description", "undeleted"] else Fore.BLUE
            video = f"  • {element.video}".ljust(82)
            kind_str = f" │ 🔥{kind.capitalize()}"
            print(colour + video + kind_str)

        for video in self.added:
            print(Fore.GREEN + f"  • {video}")

        for video in self.deleted:
            print(Fore.RED + f"  • {video}")

        if not self.added and not self.deleted and not self.updated:
            print(Style.DIM + "  • Nothing was added or deleted")

        print(_watermark())

    def add_updated(self, kind: str, element: Element):
        self.updated.append((kind, element))

    def reset(self):
        self.added = []
        self.deleted = []
        self.updated = []

    def interesting_changes(self):
        """Reports on the most interesting changes"""

        def fmt_video(video: Video) -> str:
            if (
                not video.title.changed()
                and not video.description.changed()
                and not video.deleted.changed()
            ):
                return ""

            buf: list = []
            maybe_capitalize = lambda word: word.capitalize() if len(buf) == 0 else word
            add_buf = lambda name, change, colour: buf.append(
                colour + maybe_capitalize(name) + f" x{change}" + Fore.RESET
            )

            change_deleted = sum(1 for v in video.deleted.inner.values() if v == True)
            if change_deleted:
                add_buf("deleted", change_deleted, Fore.RED)
            change_description = len(video.description.inner) - 1
            if change_description:
                add_buf("description", change_description, Fore.CYAN)
            change_title = len(video.title.inner) - 1
            if change_title:
                add_buf("title", change_title, Fore.CYAN)

            changes = ", ".join(buf) + Fore.RESET
            title = _truncate_text(video.title.current(), 51).strip()
            url = f"http://127.0.0.1:7667/channel/{video.channel}/videos/{video.id}"
            return (
                f"  • {title}\n    {changes}\n    "
                + Style.DIM + url + Style.RESET_ALL + "\n"
            )

        print(f"Finding interesting changes in {self.channel}..")

        HEADING = "Interesting videos:\n"
        buf = HEADING
        for video in self.channel.videos:
            buf += fmt_video(video)

        if buf == HEADING:
            print("No interesting videos found")
        else:
            print(buf[:-1])

        print(_watermark())


def _watermark() -> str:
    date = datetime.datetime.utcnow().isoformat()
    return Style.RESET_ALL + f"Bilark – {date}"
