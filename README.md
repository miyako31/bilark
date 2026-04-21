# Bilark

**Bilibili archiving made simple** — a fork of [yark](https://github.com/Owez/yark) adapted for Bilibili.

Bilark lets you archive a Bilibili user's video uploads, track metadata changes over time (titles, descriptions, view counts, likes), and browse your archive through a built-in web viewer — just like yark does for YouTube.

## Features

- Archive an entire Bilibili channel's video library
- Track changes to titles, descriptions, views, likes over time
- Built-in offline web viewer with video playback
- Add timestamped notes to any video
- Incremental refresh (only downloads new/changed content)
- Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp)

## Installation

```bash
pip install yt-dlp flask colorama requests progress
git clone https://github.com/your-fork/bilark
cd bilark
pip install -e .
```

## Usage

```bash
# Create a new archive (use UID or full URL)
bilark new vtuber 12345678
bilark new vtuber https://space.bilibili.com/12345678/video

# Refresh (download metadata + new videos)
bilark refresh vtuber

# Refresh with options
bilark refresh vtuber --videos=10       # limit to 10 most recent
bilark refresh vtuber --skip-download   # metadata only
bilark refresh vtuber --skip-metadata   # download only

# Launch the web viewer
bilark view vtuber

# Print a change report
bilark report vtuber
```

## Archive format

Archives are stored as a directory:

```
vtuber/
  bilark.json        # Archive metadata (version, url, video list)
  bilark.bak         # Automatic backup of previous bilark.json
  videos/            # Downloaded video files (named by BV ID)
  thumbnails/        # Downloaded thumbnail images
```

## Differences from yark

| Feature | yark | bilark |
|---|---|---|
| Platform | YouTube | Bilibili |
| Video categories | videos / shorts / livestreams | videos only |
| Video URL | `youtube.com/watch?v=...` | `bilibili.com/video/BV...` |
| Archive file | `yark.json` | `bilark.json` |
| Channel input | YouTube channel URL | Bilibili space URL or UID |

## Notes

- Some Bilibili videos (premium, region-locked) may not be downloadable without cookies.  
  Pass cookies via yt-dlp's `--cookies` mechanism or by setting `YTDL_OPTIONS` if wrapping.
- Bilibili separates audio and video streams (DASH), so ffmpeg is required for merging.
