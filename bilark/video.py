"""Single video inside of a channel (Bilibili edition)"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import requests
import hashlib
from .errors import NoteNotFoundException
from .utils import _truncate_text
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .channel import Channel



def _strip_part_title(parent_title: str, part_title: str) -> str:
    """Extract a clean short title for a part.

    yt-dlp returns part titles as "{parent} p{NN} {subtitle}".
    We strip the parent prefix and the pNN marker, returning only the subtitle.
    """
    import re as _re
    s = part_title.strip()
    if parent_title:
        pt = parent_title.strip()
        if s.startswith(pt):
            s = s[len(pt):].strip()
    s = _re.sub(r'^p[0-9]+\s*', '', s).strip()
    return s if s else part_title.strip()


class Video:
    channel: "Channel"
    id: str
    uploaded: datetime
    width: int
    height: int
    title: "Element"
    description: "Element"
    views: "Element"
    likes: "Element"
    thumbnail: "Element"
    deleted: "Element"
    notes: list
    parts: int  # Number of 分P parts (1 for single-part)
    part_titles: list  # Title of each part (empty list for single-part)

    @staticmethod
    def new(entry: dict, channel) -> "Video":
        """Create new video from yt-dlp metadata entry.

        Handles both single-part and multi-part (分P) Bilibili videos.
        For multi-part, entry may be a playlist dict with sub-entries.
        """
        video = Video()
        video.channel = channel
        video.notes = []
        video.known_not_deleted = True

        # Multi-part (分P): yt-dlp returns a playlist-type entry
        if entry.get("_type") == "playlist" and entry.get("entries"):
            sub = entry["entries"]
            first = sub[0] if sub else entry
            video.id = entry.get("id") or first.get("id", "")
            video.uploaded = _decode_date(
                entry.get("upload_date") or first.get("upload_date") or "19700101"
            )
            video.width = first.get("width") or 0
            video.height = first.get("height") or 0
            video.title = Element.new(video, entry.get("title") or first.get("title", ""))
            video.description = Element.new(video, entry.get("description") or first.get("description", ""))
            video.views = Element.new(video, entry.get("view_count") or first.get("view_count"))
            video.likes = Element.new(video, entry.get("like_count") or first.get("like_count"))
            thumb_url = entry.get("thumbnail") or first.get("thumbnail", "")
            video.thumbnail = Element.new(video, Thumbnail.new(thumb_url, video))
            video.parts = len(sub)
            video.part_titles = [_strip_part_title(entry.get("title", ""), e.get("title", f"Part {i+1}")) for i, e in enumerate(sub)]
        else:
            # Single-part
            video.id = entry.get("id", "")
            video.uploaded = _decode_date(
                entry.get("upload_date") or str(entry.get("timestamp", "19700101"))
            )
            video.width = entry.get("width") or 0
            video.height = entry.get("height") or 0
            video.title = Element.new(video, entry.get("title", ""))
            video.description = Element.new(video, entry.get("description", ""))
            video.views = Element.new(video, entry.get("view_count"))
            video.likes = Element.new(video, entry.get("like_count"))
            thumb_url = entry.get("thumbnail", "")
            video.thumbnail = Element.new(video, Thumbnail.new(thumb_url, video))
            video.parts = 1
            video.part_titles = []

        video.deleted = Element.new(video, False)
        return video

    @staticmethod
    def _new_empty() -> "Video":
        from .channel import Channel
        fake_entry = {
            "id": "BV00000000000",
            "upload_date": "19700101",
            "width": 0, "height": 0,
            "title": "", "description": "",
            "view_count": 0, "like_count": 0,
            "thumbnail": "", "formats": [],
        }
        return Video.new(fake_entry, Channel._new_empty())

    def update(self, entry: dict):
        """Updates video using fresh metadata"""
        if entry.get("_type") == "playlist" and entry.get("entries"):
            sub = entry["entries"]
            first = sub[0] if sub else entry
            self.title.update("title", entry.get("title") or first.get("title", ""))
            self.description.update("description", entry.get("description") or first.get("description", ""))
            self.views.update("view count", entry.get("view_count") or first.get("view_count"))
            self.likes.update("like count", entry.get("like_count") or first.get("like_count"))
            thumb = entry.get("thumbnail") or first.get("thumbnail", "")
            self.parts = len(sub)
            self.part_titles = [_strip_part_title(entry.get("title", ""), e.get("title", f"Part {i+1}")) for i, e in enumerate(sub)]
        else:
            self.title.update("title", entry.get("title", ""))
            self.description.update("description", entry.get("description", ""))
            self.views.update("view count", entry.get("view_count"))
            self.likes.update("like count", entry.get("like_count"))
            thumb = entry.get("thumbnail", "")
            self.parts = 1
            self.part_titles = []

        if thumb:
            self.thumbnail.update("thumbnail", Thumbnail.new(thumb, self))
        self.deleted.update("undeleted", False)
        self.known_not_deleted = True

    def filenames(self) -> list[str]:
        """Returns list of downloaded filenames for this video.

        yt-dlp names Bilibili multi-part files as:
          Single-part: BV1xxx.mp4
          Multi-part:  BV1xxx_p1.mp4, BV1xxx_p2.mp4, ...

        We match the video id exactly (single) or id + '_p' + digits (multi).
        """
        videos_dir = self.channel.path / "videos"
        found = []
        for file in videos_dir.iterdir():
            if file.suffix == ".part":
                continue
            stem = file.stem
            if stem == self.id:
                # exact match = single-part
                found.append(file.name)
            elif stem.startswith(self.id + "_p"):
                # multi-part: BV1xxx_p1, BV1xxx_p2 ...
                rest = stem[len(self.id) + 2:]  # after "_p"
                if rest.isdigit():
                    found.append(file.name)
        return sorted(found)

    def filename(self) -> Optional[str]:
        """Returns the first filename, for backwards compatibility with viewer."""
        files = self.filenames()
        return files[0] if files else None

    def downloaded(self) -> bool:
        """Returns True if all expected parts are downloaded.
        
        For multi-part videos, checks that at least `parts` files exist.
        For single-part, checks that at least 1 file exists.
        """
        files = self.filenames()
        if not files:
            return False
        # If we know the part count, verify all parts present
        if self.parts > 1:
            return len(files) >= self.parts
        return True

    def updated(self) -> bool:
        return (
            len(self.title.inner) > 1
            or len(self.description.inner) > 1
            or len(self.deleted.inner) > 1
        )

    def search(self, id: str):
        for note in self.notes:
            if note.id == id:
                return note
        raise NoteNotFoundException(f"Couldn't find note {id}")

    def url(self) -> str:
        """Returns the Bilibili watch URL for this video"""
        return f"https://www.bilibili.com/video/{self.id}"

    @staticmethod
    def _from_dict(encoded: dict, channel) -> "Video":
        video = Video()
        video.channel = channel
        video.id = encoded["id"]
        video.uploaded = datetime.fromisoformat(encoded["uploaded"])
        video.width = encoded["width"]
        video.height = encoded["height"]
        video.title = Element._from_dict(encoded["title"], video)
        video.description = Element._from_dict(encoded["description"], video)
        video.views = Element._from_dict(encoded["views"], video)
        video.likes = Element._from_dict(encoded["likes"], video)
        video.thumbnail = Thumbnail._from_element(encoded["thumbnail"], video)
        video.notes = [Note._from_dict(video, n) for n in encoded["notes"]]
        video.deleted = Element._from_dict(encoded["deleted"], video)
        video.parts = encoded.get("parts", 1)
        video.part_titles = encoded.get("part_titles", [])
        video.known_not_deleted = False
        return video

    def _to_dict(self) -> dict:
        return {
            "id": self.id,
            "uploaded": self.uploaded.isoformat(),
            "width": self.width,
            "height": self.height,
            "title": self.title._to_dict(),
            "description": self.description._to_dict(),
            "views": self.views._to_dict(),
            "likes": self.likes._to_dict(),
            "thumbnail": self.thumbnail._to_dict(),
            "deleted": self.deleted._to_dict(),
            "notes": [note._to_dict() for note in self.notes],
            "parts": self.parts,
            "part_titles": self.part_titles,
        }

    def __repr__(self) -> str:
        title = _truncate_text(self.title.current())
        views = _magnitude(self.views.current()).ljust(6)
        likes = _magnitude(self.likes.current()).ljust(6)
        width = self.width if self.width else "?"
        height = self.height if self.height else "?"
        uploaded = _encode_date_human(self.uploaded)
        parts_str = f" │ 📂{self.parts}p" if self.parts > 1 else ""
        return f"{title}  🔎{views} │ 👍{likes} │ 📅{uploaded} │ 📺{width}x{height}{parts_str}"

    def __lt__(self, other) -> bool:
        return self.uploaded < other.uploaded


def _decode_date(input: str) -> datetime:
    """Decodes date string like '20180915' or Unix timestamp"""
    if not input:
        return datetime(1970, 1, 1)
    try:
        s = str(input).strip()
        if len(s) == 8 and s.isdigit():
            return datetime.strptime(s, "%Y%m%d")
        return datetime.utcfromtimestamp(int(float(s)))
    except Exception:
        return datetime(1970, 1, 1)


def _encode_date_human(input: datetime) -> str:
    return input.strftime("%d %b %Y")


def _magnitude(count: Optional[int] = None) -> str:
    if count is None: return "?"
    elif count < 1000: return str(count)
    elif count < 1_000_000: return f"{count/1000:.1f}k"
    elif count < 1_000_000_000: return f"{count/1_000_000:.1f}m"
    else: return f"{count/1_000_000_000:.1f}b"


class Element:
    video: "Video"
    inner: dict

    @staticmethod
    def new(video: "Video", data):
        element = Element()
        element.video = video
        element.inner = {datetime.utcnow(): data}
        return element

    def update(self, kind: Optional[str], data):
        has_id = hasattr(data, "id")
        current = self.current()
        if (not has_id and current != data) or (has_id and data.id != current.id):
            self.inner[datetime.utcnow()] = data
            if kind is not None:
                self.video.channel.reporter.add_updated(kind, self)
        return self

    def current(self):
        return self.inner[list(self.inner.keys())[-1]]

    def changed(self) -> bool:
        return len(self.inner) > 1

    @staticmethod
    def _from_dict(encoded: dict, video: "Video") -> "Element":
        element = Element()
        element.video = video
        element.inner = {}
        for key in encoded:
            element.inner[datetime.fromisoformat(key)] = encoded[key]
        return element

    def _to_dict(self) -> dict:
        encoded = {}
        for date in self.inner:
            data = self.inner[date]
            data = data._to_element() if hasattr(data, "_to_element") else data
            encoded[date.isoformat()] = data
        return encoded


class Thumbnail:
    video: "Video"
    id: str
    path: Path

    @staticmethod
    def new(url: str, video: "Video") -> "Thumbnail":
        thumbnail = Thumbnail()
        thumbnail.video = video
        if not url:
            thumbnail.id = "empty"
            thumbnail.path = thumbnail._path() / "empty.webp"
            return thumbnail
        try:
            image = requests.get(url, timeout=10).content
            thumbnail.id = hashlib.blake2b(image, digest_size=20, usedforsecurity=False).hexdigest()
            thumbnail.path = thumbnail._path() / f"{thumbnail.id}.webp"
            with open(thumbnail.path, "wb+") as file:
                file.write(image)
        except Exception:
            thumbnail.id = "empty"
            thumbnail.path = thumbnail._path() / "empty.webp"
        return thumbnail

    @staticmethod
    def load(id: str, video: "Video") -> "Thumbnail":
        thumbnail = Thumbnail()
        thumbnail.id = id
        thumbnail.video = video
        thumbnail.path = thumbnail._path() / f"{thumbnail.id}.webp"
        return thumbnail

    def _path(self) -> Path:
        return self.video.channel.path / "thumbnails"

    @staticmethod
    def _from_element(element: dict, video: "Video") -> "Element":
        decoded = Element._from_dict(element, video)
        for date in decoded.inner:
            decoded.inner[date] = Thumbnail.load(decoded.inner[date], video)
        return decoded

    def _to_element(self) -> str:
        return self.id


class Note:
    video: "Video"
    id: str
    timestamp: int
    title: str
    body: Optional[str]

    @staticmethod
    def new(video: "Video", timestamp: int, title: str, body: Optional[str] = None):
        note = Note()
        note.video = video
        note.id = str(uuid4())
        note.timestamp = timestamp
        note.title = title
        note.body = body
        return note

    @staticmethod
    def _from_dict(video: "Video", element: dict) -> "Note":
        note = Note()
        note.video = video
        note.id = element["id"]
        note.timestamp = element["timestamp"]
        note.title = element["title"]
        note.body = element["body"]
        return note

    def _to_dict(self) -> dict:
        return {"id": self.id, "timestamp": self.timestamp, "title": self.title, "body": self.body}
