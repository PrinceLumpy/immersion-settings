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

Optional settings include `download_history`, `openrouter_model`,
`openrouter_api_key`, and `yt_dlp_sort`. History defaults to
`.daily-impd-history.json` beside the config file. The translation model
defaults to OpenRouter's `openrouter/free` router. The yt-dlp sort preference
defaults to `res:480,vcodec:vp9,acodec:aac,ext:mkv`, matching the example
manual-download settings below. Adjust `yt_dlp_sort` in your private config to
change the daily downloader's resolution, codecs, or container preference.
Relative paths are resolved relative to the config file. The private
`daily-impd.config` is gitignored so personal paths stay local.

The workflow uses `scripts/daily-impd/daily-impd.config` by default. To use
another config file, set `IMPD_CONFIG` to its path when running the script.

## Workflow services

The Bash script coordinates configuration, playlist history, download, and
rotation. The Python helpers live in `scripts/daily-impd/services/`:

- `config.py` reads and validates the key-value config.
- `playlist_history.py` gets playlist video IDs and tracks which ones have
  been successfully processed. It does not call the YouTube API or modify
  playlists.
- `subtitles/subtitle_workflow.py` supports two flows: the daily script checks
  YouTube captions first, while a direct invocation always transcribes the
  local video with `elevate`.
- `subtitles/subtitle_padding.py` extends generated subtitle cue timings.
- `subtitles/subtitle_translate.py` creates an English SRT with the original
  cue timings using one OpenRouter request for the complete SRT.

## Requirements

- Python 3
- `yt-dlp`, for downloading the daily video and its captions
- FFmpeg (`ffmpeg` and `ffprobe`)
- `elevate` CLI, for direct transcription or missing daily source captions
- An OpenRouter API key, for translating subtitles
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
save media when running it manually. The daily workflow uses
`--ignore-config`, so it does not inherit these manual settings. Its
`yt_dlp_sort` config option controls the daily video format selection, while
subtitle languages are selected by the workflow itself. Keep `all` if you want
every language for manual downloads; otherwise, narrow `--sub-langs` to the
languages you use.

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

## OpenRouter translation setup

Create an API key in [OpenRouter](https://openrouter.ai/). By default, the
workflow uses the `openrouter/free` router, which picks an available free model.
Free model availability, speed, and rate limits vary. To choose another model,
set `openrouter_model` in the private config; see OpenRouter's
[free-model documentation](https://openrouter.ai/docs/guides/routing/routers/free-router)
for details. The workflow sends the complete SRT, including numbering and
timestamps, in one request and writes the returned SRT directly for embedding.
There are no automatic retries. Subtitle text is sent to OpenRouter and the
model provider selected by its router.

The key is read from `OPENROUTER_API_KEY` or `openrouter_api_key` in the private
`daily-impd.config`; the environment variable takes precedence. To use an
environment variable for a manual run without putting the key in shell history:

```bash
read -rsp "OpenRouter API key: " OPENROUTER_API_KEY
printf '\n'
export OPENROUTER_API_KEY
```

Or add `openrouter_api_key=your-key` to your gitignored private config. For a
systemd service, you can instead store it in a user-only environment file:

```bash
mkdir -p ~/.config/immersion-daily
chmod 700 ~/.config/immersion-daily
install -m 600 /dev/null ~/.config/immersion-daily/credentials
nano ~/.config/immersion-daily/credentials
```

Put this line in that file:

```text
OPENROUTER_API_KEY=your-key
```

Add the following to the `[Service]` section of
`~/.config/systemd/user/immersion-daily.service`:

```ini
EnvironmentFile=%h/.config/immersion-daily/credentials
```

Then reload the user service manager with
`systemctl --user daemon-reload`. Change the model using `openrouter_model` in
`daily-impd.config`. Free model use has availability and rate limits; check
OpenRouter's terms and the selected provider's policies before sending subtitle
text.

## Run

Run the workflow manually from the repository root:

```bash
bash "scripts/daily-impd/immersion-daily.sh"
```

Each run selects the day's playlist, downloads its first unprocessed video, and
asks the subtitle service to fetch that day's target-language captions
(Japanese or Simplified Chinese) and English captions from YouTube.

- If target-language and English captions both exist, the workflow uses those
  files directly and embeds them without transcription or translation.
- If target-language captions exist but English captions do not, OpenRouter
  translates the target SRT as one complete file.
- If target-language captions do not exist, `elevate` transcribes the video
  using the playlist's language, even if YouTube has English-only captions;
  OpenRouter translates the generated SRT into English.
- The source and English SRT sidecars and matching `.transcript.json` are
  removed only after both tracks are embedded successfully. On failure,
  temporary subtitles remain for troubleshooting or retry.
- OpenRouter receives the complete SRT in one request and returns a translated
  SRT, which is passed directly to the embedding step.
- The source and English tracks are embedded in the video. The result is an
  MKV file; if the downloaded video was another format, it is replaced by the
  MKV after embedding succeeds.
- The video is recorded in local history after subtitle processing succeeds.
- Finally, the script runs `impd rotate`.

You can run the subtitle flow directly for any local video file. This mode
always transcribes the video with `elevate` instead of looking for existing
subtitles. The language argument is optional; use `jp` for Japanese or `zh`
for Chinese, or omit it to let `elevate` detect the language.

```bash
python3 "scripts/daily-impd/services/subtitles/subtitle_workflow.py" "/path/to/video.mkv"
python3 "scripts/daily-impd/services/subtitles/subtitle_workflow.py" "/path/to/video.mkv" jp
```

Direct mode sends the generated SRT in one OpenRouter translation request and
embeds both tracks in an MKV. It requires `OPENROUTER_API_KEY` or
`openrouter_api_key` in the private config.
