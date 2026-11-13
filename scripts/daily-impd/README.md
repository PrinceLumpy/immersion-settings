# Daily Immersion workflow

`immersion-daily.sh` downloads the first unprocessed video from one of two
YouTube playlists using the regular yt-dlp configuration, then runs
`impd rotate`.

## Configuration

Create your private configuration file from the example:

```bash
cp -n "scripts/daily-impd/daily-impd.config.example" \
  "scripts/daily-impd/daily-impd.config"
```

Edit `daily-impd.config` for your machine. It uses one `key=value` setting per
line; do not put spaces around the `=`. Only `destination`,
`japanese_playlist_id`, and `chinese_playlist_id` are required. Playlist values
are IDs (the text after `list=` in each playlist URL), not full URLs.

The optional `download_history` setting defaults to `.daily-impd-history.json`
beside the config file. Relative paths are resolved relative to the config file.
The private `daily-impd.config` is gitignored so personal paths stay local.

The workflow uses `scripts/daily-impd/daily-impd.config` by default. To use
another config file, set `IMPD_CONFIG` to its path when running the script.

## Workflow services

The Bash script coordinates configuration, playlist history, download, and
rotation. The Python helpers live in `scripts/daily-impd/services/`:

- `config.py` reads and validates the key-value config.
- `playlist_history.py` gets playlist video IDs and tracks which ones have
  been successfully downloaded. It does not call the YouTube API or modify
  playlists.

## Requirements

- Python 3
- `yt-dlp`, for downloading the daily video
- The `impd` command, used at the end of the daily script

## Install and configure `yt-dlp`

Follow the [official yt-dlp installation guide](https://github.com/yt-dlp/yt-dlp/wiki/Installation).
On Linux, install it with your package manager or the recommended standalone
binary/pipx method, then verify it is available with:

```bash
yt-dlp --version
```

The daily workflow uses the regular yt-dlp configuration. See the
[configuration documentation](https://github.com/yt-dlp/yt-dlp#configuration)
for platform-specific config locations. For example, on Linux create
`~/.config/yt-dlp/config` with:

```text
-S res:480,vcodec:vp9,acodec:aac,ext:mkv
--merge-output-format mkv
-o path-to-active-immersion/%(title)s.%(ext)s
```

Replace `path-to-active-immersion` with the directory where yt-dlp should save
media, and set `destination` in `daily-impd.config` to the same directory.

## Download history

The workflow does not modify YouTube playlists or require Google OAuth. It
checks the selected playlist for the first video not yet recorded in its local
history, then records that video's ID after the download succeeds. You do not
need to track completed videos or remove them manually; you can remove them
from YouTube separately if you want to keep the playlist tidy.

By default, history is saved as `.daily-impd-history.json` beside the config
file. The history file is gitignored. Set `download_history` in
`daily-impd.config` to store it elsewhere. History is kept separately for each
playlist. If all videos in a playlist have been processed, the workflow reports
that there is nothing to do and exits successfully. Keep the history file to
prevent already-processed videos from being selected again.

## Run

Run the workflow manually from the repository root:

```bash
bash "scripts/daily-impd/immersion-daily.sh"
```

Each run selects the day's playlist, downloads its first unprocessed video
using yt-dlp's regular configuration, records the video in local history after
the download succeeds, and runs `impd rotate`.
