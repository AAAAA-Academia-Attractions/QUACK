#!/usr/bin/env bash
# Generate video.mp4 from god-view frames for each run directory.
#
# Scans game_logs/ (or a given directory) for renders/god_view/ folders
# that contain frames but have no sibling video.mp4 yet.
#
# Usage:
#   ./scripts/generate_videos.sh                          # all runs under game_logs/
#   ./scripts/generate_videos.sh game_logs/homogeneous/gpt5.2/  # specific subtree
#   ./scripts/generate_videos.sh -f 2                     # 2 fps
#   ./scripts/generate_videos.sh --force                  # regenerate existing videos
set -euo pipefail

FPS=1
FORCE=false
SEARCH_DIR="game_logs"

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [DIRECTORY]

Generate video.mp4 from god-view frames for each experiment run.

Options:
  -f, --fps N    Frames per second (default: $FPS)
  --force        Regenerate even if video.mp4 already exists
  -h, --help     Show this help

Examples:
  $(basename "$0")                                        # all runs, 1 fps
  $(basename "$0") game_logs/homogeneous/gpt5.2/          # specific model
  $(basename "$0") -f 2                                   # 2 fps
  $(basename "$0") --force game_logs/homogeneous/gpt5.2/  # regenerate all
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--fps)   FPS="$2"; shift 2 ;;
        --force)    FORCE=true; shift ;;
        -h|--help)  usage ;;
        *)          SEARCH_DIR="$1"; shift ;;
    esac
done

if ! command -v ffmpeg &>/dev/null; then
    echo "ERROR: ffmpeg is not installed. Install it first."
    exit 1
fi

total=0
generated=0
skipped=0
failed=0

while IFS= read -r god_view_dir; do
    run_dir="$(dirname "$(dirname "$god_view_dir")")"
    video_path="$run_dir/video.mp4"

    total=$((total + 1))

    if [ "$FORCE" = false ] && [ -f "$video_path" ]; then
        skipped=$((skipped + 1))
        continue
    fi

    frame_count=$(ls "$god_view_dir"/frame_*.png 2>/dev/null | wc -l | tr -d ' ')
    if [ "$frame_count" -eq 0 ]; then
        skipped=$((skipped + 1))
        continue
    fi

    echo -n "  $(basename "$run_dir") ($frame_count frames) ... "
    if ffmpeg -y -framerate "$FPS" \
        -i "$god_view_dir/frame_%04d.png" \
        -c:v libx264 -pix_fmt yuv420p \
        -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" \
        "$video_path" \
        </dev/null >/dev/null 2>&1; then
        echo "OK"
        generated=$((generated + 1))
    else
        echo "FAILED"
        failed=$((failed + 1))
    fi
done < <(find "$SEARCH_DIR" -type d -name "god_view" | sort)

echo ""
echo "Done: $generated generated, $skipped skipped, $failed failed (out of $total runs)"
