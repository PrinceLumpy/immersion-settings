#!/bin/bash
dir="${1:-.}"
find "$dir" -type f -name "*.mp3" -print0 | while IFS= read -r -d '' f; do
  ffmpeg -nostdin -loglevel error -y -i "$f" -c:a libvorbis -q:a 3 "${f%.mp3}.ogg"
done