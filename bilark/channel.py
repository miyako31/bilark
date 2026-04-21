"""Channel and overall archive management with downloader (Bilibili edition)"""

from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path
import time
from yt_dlp import YoutubeDL, DownloadError  # type: ignore
from colorama import Style, Fore
import sys
from .reporter import Reporter
from .errors import ArchiveNotFoundException, _err_msg, VideoNotFoundException
from .video import Video, Element
from typing import Any, Optional
from progress.spinner import PieSpinner
from concurrent.futures import ThreadPoolExecutor

ARCHIVE_COMPAT = 1
"""
Version of Bilark archives.
- Version 1: Initial Bilibili format. Single 'videos' list.
  Uses Bilibili space URL (https://space.bilibili.com/<UID>/video) and BV-number IDs.
"""


class DownloadConfig:
    max_videos: Optional[int]
    skip_download: bool
    skip_metadata: bool
    format: Optional[str]

    def __init__(self) -> None:
        self.max_videos = None
        self.skip_download = False
        self.skip_metadata = False
        self.format = None

    def submit(self):
        if self.max_videos == 0:
            print(Fore.YELLOW + "Using skip-download is recommended over setting max to 0" + Fore.RESET)
            self.skip_download = True


class VideoLogger:
    @staticmethod
    def downloading(d):
        id = d["info_dict"].get("id", "?")
        # For multi-part videos, show part info
        part = d["info_dict"].get("playlist_index")
        id_str = f"{id} (p{part})" if part else id
        if d["status"] == "downloading":
            percent = d["_percent_str"].strip()
            print(Style.DIM + f"  • Downloading {id_str}, at {percent}..                " + Style.NORMAL, end="\r")
        elif d["status"] == "finished":
            print(Style.DIM + f"  • Downloaded {id_str}                " + Style.NORMAL)

    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


class Channel:
    path: Path
    version: int
    url: str
    videos: list
    reporter: Reporter

    @staticmethod
    def new(path: Path, url: str) -> "Channel":
        print("Creating new channel..")
        channel = Channel()
        channel.path = Path(path)
        channel.version = ARCHIVE_COMPAT
        channel.url = _normalize_bilibili_url(url)
        channel.videos = []
        channel.reporter = Reporter(channel)
        channel.commit()
        return channel

    @staticmethod
    def _new_empty() -> "Channel":
        return Channel.new(Path("pretend"), "https://space.bilibili.com/0/video")

    @staticmethod
    def load(path: Path) -> "Channel":
        path = Path(path)
        channel_name = path.name
        print(f"Loading {channel_name} channel..")
        if not path.exists():
            raise ArchiveNotFoundException("Archive doesn't exist")
        encoded = json.load(open(path / "bilark.json", "r"))
        archive_version = encoded["version"]
        if archive_version != ARCHIVE_COMPAT:
            _err_msg(f"Archive version v{archive_version} not supported (expected v{ARCHIVE_COMPAT})", True)
            sys.exit(1)
        return Channel._from_dict(encoded, path)

    def metadata(self):
        """Queries Bilibili for all channel metadata"""
        msg = "Downloading metadata.."
        print(msg, end="\r")
        with ThreadPoolExecutor() as ex:
            future = ex.submit(self._download_metadata)
            with PieSpinner(f"{msg} ") as bar:
                no_bar_time = time.time() + 2
                while time.time() < no_bar_time:
                    if future.done(): break
                    time.sleep(0.25)
                while not future.done():
                    bar.next()
                    time.sleep(0.075)
            res = future.result()
        self._parse_metadata(res)

    def _download_metadata(self) -> list[dict]:
        """
        Downloads full metadata for every video in the channel.

        Strategy:
        1. First pass with extract_flat=True to get the list of BV IDs quickly.
        2. Second pass: for each BV ID, call extract_info (without extract_flat)
           so we get complete info including multi-part (分P) entries.

        Returns a flat list of fully-resolved entry dicts.

        Bilibili error 352 (Bot detection) の対策:
        - BILIBILI_COOKIES 環境変数にcookies.txtのパスを設定する
        - またはブラウザから自動取得する (--cookies-from-browser chrome)
        """
        import os

        cookie_file = os.environ.get("BILIBILI_COOKIES")

        common_opts = {
            "logger": VideoLogger(),
            "ignore_no_formats_error": True,
            "quiet": True,
            # ブラウザになりすましてBot検出を回避
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.bilibili.com/",
            },
        }
        if cookie_file:
            common_opts["cookiefile"] = cookie_file

        # --- Step 1: flat listing to collect BV URLs ---
        flat_settings = {**common_opts, "extract_flat": True}

        flat_res: dict[str, Any] = {}
        with YoutubeDL(flat_settings) as ydl:
            for i in range(3):
                try:
                    flat_res = ydl.extract_info(self.url, download=False)
                    break
                except Exception as e:
                    retrying = i != 2
                    _err_dl("metadata (flat)", e, retrying)
                    if retrying:
                        print(Style.DIM + "  • Retrying flat metadata.." + Style.RESET_ALL)

        flat_entries = flat_res.get("entries", [])
        total = len(flat_entries)
        print(f"  Found {total} video entries, fetching full metadata..")

        # --- Step 2: full info per video (supports 分P multi-part) ---
        full_settings = {**common_opts}

        resolved: list[dict] = []
        with YoutubeDL(full_settings) as ydl:
            for idx, flat_entry in enumerate(flat_entries):
                url = flat_entry.get("url") or flat_entry.get("webpage_url")
                if not url:
                    continue
                print(f"  • Fetching [{idx+1}/{total}] {flat_entry.get('title', url)[:60]}..                ", end="\r")
                for attempt in range(3):
                    try:
                        full = ydl.extract_info(url, download=False)
                        if full:
                            resolved.append(full)
                        break
                    except Exception as e:
                        retrying = attempt != 2
                        if retrying:
                            time.sleep(3)
                        else:
                            print(Fore.YELLOW + f"\n  • Skipping {url} (failed after 3 attempts): {e}" + Fore.RESET)

        print(f"  Metadata fetched for {len(resolved)} videos.          ")
        return resolved


    def _parse_metadata(self, entries: list[dict]):
        """Parses list of fully-resolved entries into self.videos"""
        self._parse_metadata_videos("video", entries, self.videos)
        self._report_deleted(self.videos)

    def download(self, config: DownloadConfig):
        """Downloads all videos which haven't already been downloaded.
        
        Bilibili分P (multi-part) videos are handled by yt-dlp natively when
        given the video's webpage URL; all parts are downloaded automatically.
        The outtmpl uses %(id)s for single-part and %(id)s_p%(playlist_index)s
        for multi-part videos.
        """
        import os
        self._clean_parts()

        cookie_file = os.environ.get("BILIBILI_COOKIES")

        settings = {
            # For single-part: NTE/videos/BV1xxx.mp4
            # For multi-part: NTE/videos/BV1xxx_p1.mp4, BV1xxx_p2.mp4 ...
            "outtmpl": f"{self.path}/videos/%(id)s.%(ext)s",
            "logger": VideoLogger(),
            "progress_hooks": [VideoLogger.downloading],
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.bilibili.com/",
            },
        }
        if cookie_file:
            settings["cookiefile"] = cookie_file
        if config.format is not None:
            settings["format"] = config.format

        with YoutubeDL(settings) as ydl:
            for i in range(5):
                try:
                    not_downloaded = self._curate(config)
                    if not not_downloaded: break
                    if i == 0:
                        n = "a new video" if len(not_downloaded) == 1 else f"{len(not_downloaded)} new videos"
                        print(f"Downloading {n}..")
                    while True:
                        try:
                            ydl.download([v.url() for v in not_downloaded])
                            break
                        except DownloadError as e:
                            if "Private" in e.msg or "removed" in e.msg or "deleted" in e.msg:
                                not_downloaded, video = _skip_video(not_downloaded, "deleted")
                                if video.deleted.current() == False:
                                    self.reporter.deleted.append(video)
                                    video.deleted.update(None, True)
                            elif " bytes, expected " in e.msg:
                                not_downloaded, _ = _skip_video(not_downloaded, "no format; install ffmpeg!", True)
                            else:
                                raise e
                    break
                except Exception as e:
                    if i == 0: print()
                    _err_dl("videos", e, i != 4)

    def search(self, id: str):
        for video in self.videos:
            if video.id == id:
                return video
        raise VideoNotFoundException(f"Couldn't find {id} inside archive")

    def _curate(self, config: DownloadConfig) -> list:
        """Curate videos which aren't fully downloaded.
        
        For multi-part videos, checks that ALL parts exist.
        """
        available = self.videos
        if config.max_videos is not None:
            fixed = min(max(len(available) - 1, 0), config.max_videos)
            available = available[:fixed]
        return [v for v in available if not v.downloaded()]

    def commit(self):
        self._backup()
        print(f"Committing {self} to file..")
        for path in [self.path, self.path / "thumbnails", self.path / "videos"]:
            if not path.exists():
                path.mkdir()
        with open(self.path / "bilark.json", "w+") as file:
            json.dump(self._to_dict(), file)

    def _parse_metadata_videos(self, kind: str, entries: list, bucket: list):
        msg = f"Parsing {kind} metadata.."
        print(msg, end="\r")
        with ThreadPoolExecutor() as ex:
            future = ex.submit(self._parse_metadata_videos_comp, entries, bucket)
            with PieSpinner(f"{msg} ") as bar:
                no_bar_time = time.time() + 2
                while time.time() < no_bar_time:
                    if future.done(): return
                    time.sleep(0.25)
                while not future.done():
                    time.sleep(0.075)
                    bar.next()

    def _parse_metadata_videos_comp(self, entries: list, bucket: list):
        for entry in entries:
            if not entry:
                continue
            # Multi-part (分P) video: entry has 'entries' sub-list
            if entry.get("_type") == "playlist" and entry.get("entries"):
                # Treat the whole playlist as one Video entry, using the parent BV id
                if not entry.get("formats") and not entry.get("id"):
                    continue
            # Skip if no id
            if not entry.get("id"):
                continue

            updated = False
            for video in bucket:
                if video.id == entry["id"]:
                    video.update(entry)
                    updated = True
                    break
            if not updated:
                video = Video.new(entry, self)
                bucket.append(video)
                self.reporter.added.append(video)
        bucket.sort(reverse=True)

    def _report_deleted(self, videos: list):
        for video in videos:
            if video.deleted.current() == False and not video.known_not_deleted:
                self.reporter.deleted.append(video)
                video.deleted.update(None, True)

    def _clean_parts(self):
        bucket = []
        videos = self.path / "videos"
        for file in videos.iterdir():
            if file.suffix in (".part", ".ytdl"):
                bucket.append(file)
        if bucket:
            print("Cleaning out previous temporary files..")
            for file in bucket:
                file.unlink()

    def _backup(self):
        archive_path = self.path / "bilark.json"
        if not archive_path.exists():
            return
        with open(archive_path, "r") as f:
            save = f"// Backup of a Bilark archive, dated {datetime.utcnow().isoformat()}\n// Remove these comments and rename to 'bilark.json' to restore\n{f.read()}"
        with open(self.path / "bilark.bak", "w+") as f:
            f.write(save)

    @staticmethod
    def _from_dict(encoded: dict, path: Path) -> "Channel":
        channel = Channel()
        channel.path = path
        channel.version = encoded["version"]
        channel.url = encoded["url"]
        channel.reporter = Reporter(channel)
        channel.videos = [Video._from_dict(v, channel) for v in encoded["videos"]]
        return channel

    def _to_dict(self) -> dict:
        return {
            "version": self.version,
            "url": self.url,
            "videos": [v._to_dict() for v in self.videos],
        }

    def __repr__(self) -> str:
        return self.path.name


def _normalize_bilibili_url(url: str) -> str:
    """Normalize various Bilibili user inputs to a space/video URL"""
    url = url.strip()
    if url.isdigit():
        return f"https://space.bilibili.com/{url}/video"
    if "space.bilibili.com" in url and "/video" not in url:
        return url.rstrip("/") + "/video"
    return url


def _skip_video(videos: list, reason: str, warning: bool = False):
    for ind, video in enumerate(videos):
        if not video.downloaded():
            if warning:
                print(Fore.YELLOW + f"  • Skipping {video.id} ({reason})" + Fore.RESET, file=sys.stderr)
            else:
                print(Style.DIM + f"  • Skipping {video.id} ({reason})" + Style.NORMAL)
            return videos[ind + 1:], video
    raise Exception("Expected to skip a video but nothing found")


def _err_dl(name: str, exception: Exception, retrying: bool):
    msg = f"Unknown error whilst downloading {name}:\n{exception}"
    if isinstance(exception, DownloadError):
        m = exception.msg
        if "nodename nor servname" in m: msg = "Issue connecting with Bilibili's servers"
        elif "500" in m: msg = "Fault with Bilibili's servers"
        elif "read operation timed out" in m: msg = "Timed out downloading video"
        elif "No such file" in m: msg = "Video deleted whilst downloading"
        elif "404" in m: msg = "Couldn't find channel or video"
        elif "timed out" in m: msg = "Timed out reaching Bilibili"

    suffix = ", retrying in a few seconds.." if retrying else ""
    print(Fore.YELLOW + "  • " + msg + suffix.ljust(40) + Fore.RESET, file=sys.stderr)
    if retrying:
        time.sleep(5)
    else:
        _err_msg(f"  • Sorry, failed to download {name}", True)
        sys.exit(1)
