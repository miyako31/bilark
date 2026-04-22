# Bilark

**Bilibili archiving made simple** — a fork of [yark](https://github.com/Owez/yark) adapted for Bilibili (哔哩哔哩).

---

## ⚠️ Important Disclaimers

**This software was entirely vibe-coded by [Claude Sonnet 4.6](https://www.anthropic.com/claude).**
No human code review, test design, or quality assurance of any kind has been performed.

- **No warranty is provided.** Bugs, data loss, and unexpected behaviour may occur at any time.
- **The author and Claude accept no responsibility whatsoever for any damage or loss** resulting from the use of this software. Use entirely at your own risk.
- **This project's only connection to yark is code derivation.** It has no affiliation with, endorsement from, or support from the yark authors or contributors.
- Please comply with Bilibili's Terms of Service. Downloaded content should be used for personal viewing purposes only. Respect copyright.

---

## Overview

Bilark automatically archives a Bilibili channel's video library and lets you browse it offline through a built-in web viewer.

- Archive all videos from a Bilibili channel
- Track changes to titles, descriptions, view counts, and like counts over time
- Full support for multi-part (分P) videos
- Built-in offline web viewer with in-browser playback and part-switching UI
- Incremental refresh — only downloads new content
- Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp)

---

## Installation

```bash
# Install dependencies (ffmpeg is also required — install via your system package manager)
pip install yt-dlp flask colorama requests progress

# Install bilark
git clone https://github.com/miyako31/bilark
cd bilark
pip install -e .
```

---

## Usage

```bash
# Create a new archive (accepts UID or full URL)
bilark new vtuber 12345678
bilark new vtuber https://space.bilibili.com/12345678/video

# Refresh metadata and download new videos
bilark refresh vtuber

# Refresh with options
bilark refresh vtuber --videos=10              # limit to 10 most recent
bilark refresh vtuber --skip-download          # metadata only
bilark refresh vtuber --cookies=~/cookies.txt  # pass login cookies

# Launch the offline web viewer (opens browser automatically)
bilark view vtuber

# Print a change report
bilark report vtuber
```

---

## Dealing with Error 352 (Bot Detection)

Bilibili may block unauthenticated requests. Passing your browser cookies resolves this.

1. Export your cookies as `cookies.txt` (Netscape format) using a browser extension such as *Get cookies.txt LOCALLY* for Chrome.
2. Pass them to bilark in one of two ways:

```bash
# Per-command
bilark refresh vtuber --cookies=/path/to/cookies.txt

# Permanently via environment variable (add to .bashrc / .zshrc)
export BILIBILI_COOKIES=/path/to/cookies.txt
```

---

## Archive Structure

```
vtuber/
├── bilark.json       ← Archive metadata (version, URL, video list)
├── bilark.bak        ← Automatic backup of the previous bilark.json
├── videos/           ← Downloaded video files
│   ├── BV1xxx.mp4
│   ├── BV1yyy_p1.mp4   ← multi-part video
│   └── BV1yyy_p2.mp4
└── thumbnails/       ← Thumbnail images
```

---

## Notes

- **ffmpeg is required.** Bilibili uses DASH streaming (separate video and audio streams); ffmpeg merges them.
- Keep yt-dlp up to date: `pip install -U yt-dlp`
- Premium and region-locked content requires valid login cookies.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
