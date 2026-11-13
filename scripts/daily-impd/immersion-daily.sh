#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICES_DIR="$SCRIPT_DIR/services"
CONFIG_FILE="${IMPD_CONFIG:-$SCRIPT_DIR/daily-impd.config}"

config_value() {
  IMPD_CONFIG="$CONFIG_FILE" python3 "$SERVICES_DIR/config.py" get "$1"
}

config_path() {
  IMPD_CONFIG="$CONFIG_FILE" python3 "$SERVICES_DIR/config.py" path "$1"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    return 1
  fi
}

load_configuration() {
  require_command python3
  require_command yt-dlp
  require_command impd

  DESTINATION="$(config_path destination)"
  HISTORY_FILE="$(config_path download_history)"
  JAPANESE_PLAYLIST_ID="$(config_value japanese_playlist_id)"
  CHINESE_PLAYLIST_ID="$(config_value chinese_playlist_id)"
}

select_todays_playlist() {
  local day_of_year
  day_of_year="$(date +%j)"

  if (( 10#$day_of_year % 2 == 0 )); then
    PLAYLIST_ID="$JAPANESE_PLAYLIST_ID"
  else
    PLAYLIST_ID="$CHINESE_PLAYLIST_ID"
  fi
}

find_next_video() {
  python3 "$SERVICES_DIR/playlist_history.py" next "$PLAYLIST_ID" "$HISTORY_FILE"
}

download_video() {
  local video_id="$1"
  local video_url="https://www.youtube.com/watch?v=$video_id"

  yt-dlp "$video_url"
}

main() {
  local video_id

  load_configuration
  select_todays_playlist
  mkdir -p -- "$DESTINATION"

  video_id="$(find_next_video)"
  if [[ -z "$video_id" ]]; then
    echo "No unprocessed videos in today's playlist; nothing to do."
    return 0
  fi
  echo "Downloading video $video_id from the selected playlist."
  echo "Downloading video $video_id from the selected playlist."
  download_video "$video_id"

  # Record only successful downloads so a failed run retries the same video.
  echo "Recording video $video_id in download history."
  python3 "$SERVICES_DIR/playlist_history.py" mark \
    "$PLAYLIST_ID" "$video_id" "$HISTORY_FILE"

  echo "Running impd rotate."
  impd rotate
  echo "Daily immersion workflow completed."
}

main "$@"
