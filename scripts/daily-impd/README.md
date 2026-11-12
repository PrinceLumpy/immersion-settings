# Daily Immersion workflow

`immersion-daily.sh` downloads the first unprocessed video from one of two
YouTube playlists, gets or creates subtitles, and then runs `impd rotate`.

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

Optional settings include `download_history`, `ollama_model`, `ollama_host`,
and `yt_dlp_sort`. History defaults to `.daily-impd-history.json` beside the
config file; the model and Ollama host default to `qwen2.5:7b` and
`http://localhost:11434`. The yt-dlp sort preference defaults to
`res:480,vcodec:vp9,acodec:aac,ext:mkv`, matching the example manual-download
settings below. Adjust `yt_dlp_sort` in your private config to change the
daily downloader's resolution, codecs, or container preference. Relative paths
are resolved relative to the config file. The private `daily-impd.config` is
gitignored so personal paths stay local.

The workflow uses `scripts/daily-impd/daily-impd.config` by default. To use
another config file, set `IMPD_CONFIG` to its path when running the script.

## Workflow services

The Bash script coordinates configuration, playlist history, download, and
rotation. The Python helpers live in `scripts/daily-impd/services/`:

- `config.py` reads and validates the key-value config.
- `playlist_history.py` gets playlist video IDs and tracks which ones have
  been successfully processed. It does not call the YouTube API or modify
  playlists.
- `subtitles/subtitle_workflow.py` transcribes a local video with `elevate`,
  translates the transcription into English, and embeds both subtitle tracks.
- `subtitles/subtitle_padding.py` extends generated subtitle cue timings.
- `subtitles/subtitle_translate.py` creates an English SRT with the original
  cue timings using Ollama.

## Requirements

- Python 3
- `yt-dlp`
- FFmpeg (`ffmpeg` and `ffprobe`)
- `elevate` CLI, for transcribing videos without source-language captions
- Ollama, when English subtitles need to be translated
- The `impd` command, used at the end of the daily script

## Install and configure `yt-dlp`

Follow the [official yt-dlp installation guide](https://github.com/yt-dlp/yt-dlp/wiki/Installation).
On Linux, install it with your package manager or the recommended standalone
binary/pipx method, then verify it is available with:

```bash
yt-dlp --version
```

You can set default options in yt-dlp's configuration file for manual
downloads. See the
[configuration documentation](https://github.com/yt-dlp/yt-dlp#configuration)
for platform-specific config locations. For example, on Linux create
`~/.config/yt-dlp/config` with:

```text
-S res:480,vcodec:vp9,acodec:aac,ext:mkv
--sub-langs all,-live_chat
--embed-subs
--merge-output-format mkv
-o path-to-active-immersion/%(title)s.%(ext)s
```

Replace `path-to-active-immersion` with the directory where you want yt-dlp to
save media when running it manually. The daily workflow uses `--ignore-config`, so it does not inherit these manual
settings. Its `yt_dlp_sort` config option controls the daily video format
selection, while subtitle languages are selected by the workflow itself.
Keep `all` if you want every language for manual downloads; otherwise, narrow
`--sub-langs` to the languages you use.

## `elevate`

See the [`elevate` GitHub repository](https://github.com/Ajatt-Tools/elevate)
for installation and configuration. Move the built `elevate` executable to
`/usr/local/bin/elevate`. If `/usr/local/bin` is not already on your `PATH`, add
this line to `~/.bashrc` and reload it with `source ~/.bashrc`:

```bash
export PATH="/usr/local/bin:$PATH"
```

## Download history

The workflow does not modify YouTube playlists or require Google OAuth. It
checks the selected playlist for the first video not yet recorded in its local
history, then records that video's ID after subtitles are successfully
prepared. You do not need to track completed videos or remove them manually;
you can remove them from YouTube separately if you want to keep the playlist
tidy.

By default, history is saved as `.daily-impd-history.json` beside the config
file. The history file is gitignored. Set `download_history` in
`daily-impd.config` to store it elsewhere. History is kept separately for each
playlist. If all videos in a playlist have been processed, the workflow reports
that there is nothing to do and exits successfully. Keep the history file to
prevent already-processed videos from being selected again.

## Ollama setup

Install [Ollama](https://ollama.com/download/linux), start its local service,
and download the default translation model:

```bash
ollama pull qwen2.5:7b
ollama run qwen2.5:7b
```

Exit the model prompt with `/bye`. Configure `ollama_model` and `ollama_host`
in `daily-impd.config` if you want to use another model or Ollama server.

The model runs locally; there is no per-request translation API charge. The
model download uses disk space, and translation speed depends on the computer.

## Run

Run the workflow manually from the repository root:

```bash
bash "scripts/daily-impd/immersion-daily.sh"
```

Each run selects the day's playlist, downloads its first unprocessed video, and
runs the subtitle service on the local video file. `elevate` detects the spoken
language automatically.

- `elevate` creates a source-language SRT, which is padded by half a second
  where possible. Its matching `.transcript.json` is deleted.
- Ollama translates that transcription into English without requiring a
  specified source language.
- The source and English tracks are embedded in the video. The result is an
  MKV file; if the downloaded video was another format, it is replaced by the
  MKV after embedding succeeds.
- The video is recorded in local history after subtitle processing succeeds.
- Finally, the script runs `impd rotate`.

You can run the complete subtitle flow directly for any local video file. The
command needs only the path; `elevate` detects the language:

```bash
python3 "scripts/daily-impd/services/subtitles/subtitle_workflow.py" "/path/to/video.mkv"
```

The service does not check YouTube or existing subtitle tracks. It always
transcribes the local video, translates that transcription into English, then
embeds both tracks in an MKV. It requires the same `daily-impd.config` for
Ollama settings.
