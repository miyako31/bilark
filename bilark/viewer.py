"""Flask-based web viewer for bilark (Bilibili edition)"""

import json
import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, Blueprint
import logging
from .errors import ArchiveNotFoundException, NoteNotFoundException, VideoNotFoundException, TimestampException
from .channel import Channel
from .video import Note

routes = Blueprint("routes", __name__, template_folder="templates")


@routes.route("/", methods=["POST", "GET"])
def index():
    if request.method == "POST":
        name = request.form["channel"]
        return redirect(url_for("routes.channel", name=name))
    else:
        visited = request.cookies.get("visited")
        if visited is not None:
            visited = json.loads(visited)
        error = request.args.get("error")
        return render_template("index.html", error=error, visited=visited)


@routes.route("/channel/<n>")
def channel_empty(n):
    return redirect(url_for("routes.channel", n=n))


@routes.route("/channel/<n>/videos")
def channel(n):
    try:
        ch = Channel.load(n)
        ldir = os.listdir(ch.path / "videos")
        return render_template("channel.html", title=n, channel=ch, name=n, ldir=ldir)
    except ArchiveNotFoundException:
        return redirect(url_for("routes.index", error="Couldn't open channel's archive"))
    except Exception as e:
        return redirect(url_for("routes.index", error=f"Internal server error:\n{e}"))


@routes.route("/channel/<n>/videos/<id>", methods=["GET", "POST", "PATCH", "DELETE"])
def video(n, id):
    try:
        ch = Channel.load(n)
        vid = ch.search(id)

        if request.method == "GET":
            title = f"{vid.title.current()} · {n}"
            views_data = json.dumps(vid.views._to_dict())
            likes_data = json.dumps(vid.likes._to_dict())
            return render_template("video.html", title=title, name=n, video=vid,
                                   views_data=views_data, likes_data=likes_data,
                                   filenames=vid.filenames())

        elif request.method == "POST":
            new = request.get_json()
            if "title" not in new:
                return "Invalid schema", 400
            timestamp = _decode_timestamp(new["timestamp"])
            note = Note.new(vid, timestamp, new["title"], new.get("body"))
            vid.notes.append(note)
            vid.channel.commit()
            return note._to_dict(), 200

        elif request.method == "PATCH":
            update = request.get_json()
            if "id" not in update or ("title" not in update and "body" not in update):
                return "Invalid schema", 400
            try:
                note = vid.search(update["id"])
            except NoteNotFoundException:
                return "Note not found", 404
            if "title" in update: note.title = update["title"]
            if "body" in update: note.body = update["body"]
            vid.channel.commit()
            return "Updated", 200

        elif request.method == "DELETE":
            delete = request.get_json()
            if "id" not in delete:
                return "Invalid schema", 400
            vid.notes = [n for n in vid.notes if n.id != delete["id"]]
            vid.channel.commit()
            return "Deleted", 200

    except ArchiveNotFoundException:
        return redirect(url_for("routes.index", error="Couldn't open channel's archive"))
    except VideoNotFoundException:
        return redirect(url_for("routes.index", error="Couldn't find video in archive"))
    except TimestampException:
        return "Invalid timestamp", 400
    except Exception as e:
        return redirect(url_for("routes.index", error=f"Internal server error:\n{e}"))


@routes.route("/archive/<n>/video/<file>")
def archive_video(n, file):
    return send_from_directory(os.getcwd(), f"{n}/videos/{file}")


@routes.route("/archive/<n>/thumbnail/<id>")
def archive_thumbnail(n, id):
    return send_from_directory(os.getcwd(), f"{n}/thumbnails/{id}.webp")


def viewer() -> Flask:
    app = Flask(__name__)
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.register_blueprint(routes)

    @app.template_filter("timestamp")
    def _jinja2_filter_timestamp(timestamp, fmt=None):
        return _encode_timestamp(timestamp)

    return app


def _decode_timestamp(input: str) -> int:
    input = input.strip()
    if input == "":
        raise TimestampException("No input provided")
    splitted = input.split(":")
    splitted.reverse()
    if len(splitted) > 3:
        raise TimestampException("Days and onwards aren't supported")
    secs = 0
    try:
        secs += int(splitted[0])
        if len(splitted) > 1: secs += int(splitted[1]) * 60
        if len(splitted) > 2: secs += int(splitted[2]) * 60 * 60
    except:
        raise TimestampException("Only numbers are allowed in timestamps")
    return secs


def _encode_timestamp(timestamp: int) -> str:
    parts = []
    if timestamp >= 3600:
        hours = timestamp // 3600
        parts.append(str(hours).rjust(2, "0"))
        timestamp %= 3600
    minutes = timestamp // 60
    if parts or minutes:
        parts.append(str(minutes).rjust(2, "0"))
    timestamp %= 60
    if not parts:
        parts.append("00")
    parts.append(str(timestamp).rjust(2, "0"))
    return ":".join(parts)
