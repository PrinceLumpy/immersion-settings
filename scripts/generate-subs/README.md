# Subtitle scripts

These utilities transcribe a local video, pad the source subtitle timings, and
translate the source subtitles into English with OpenRouter. They are
independent of the daily download workflow in `scripts/daily-impd/`.

## Requirements

- Python 3
- `elevate` CLI, for transcription
- An OpenRouter API key, for translation

See the [`elevate` GitHub repository](https://github.com/Ajatt-Tools/elevate)
for installation and configuration.

## Configure OpenRouter

Copy the example config and add your OpenRouter API key:

```bash
cp -n scripts/generate-subs/subtitle.config.example \
  scripts/generate-subs/subtitle.config
```

Edit `subtitle.config` and replace `YOUR_OPENROUTER_API_KEY` with your key.
Optionally set `openrouter_model`; it defaults to `openrouter/free`. The
private config file is gitignored.

## Run

Run from the repository root to transcribe a video, pad the generated SRT, and
translate it into English:

```bash
python3 scripts/generate-subs/subtitle_workflow.py "/path/to/video.mkv"
```

The source subtitles are saved as `video.srt`; the English translation is saved
as `video.en.srt`.

To extract hardcoded subtitles with VideoSubFinder and RapidVideOCR, run:

```bash
vsf-ocr "/path/to/video.mkv"
```

The recognized subtitles are saved beside the video as `video.srt`. VideoSubFinder's
image output is kept in a temporary directory beside the video and removed after
OCR finishes, so there is no need to clear old generated-image directories. This
needs image output; do not use VideoSubFinder's `-dsi` option. If `video.srt`
already exists, the command stops rather than replacing it; pass `--force` to
overwrite it.

Install the `vsf-ocr` command once from the repository root:

```bash
chmod +x scripts/generate-subs/extract_hard_subtitles.py
ln -s "$PWD/scripts/generate-subs/extract_hard_subtitles.py" \
  "$HOME/.local/bin/vsf-ocr"
```

The helper scripts can also be run individually:

```bash
python3 scripts/generate-subs/subtitle_padding.py input.srt
python3 scripts/generate-subs/subtitle_translate.py input.srt output.en.srt
```
