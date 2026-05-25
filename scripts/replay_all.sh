#!/usr/bin/env bash
# Re-render god-view frames and video.mp4 for every game.jsonl under game_logs/.
#
# Usage:
#   ./scripts/replay_all.sh                          # all runs (1 fps)
#   ./scripts/replay_all.sh game_logs/homogeneous/   # subtree only
#   ./scripts/replay_all.sh -f 2                     # custom fps
set -uo pipefail  # keep going if one game fails

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

LOG_ROOT="game_logs"
FPS=1

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [LOG_ROOT]

Re-render renders/god_view/ and video.mp4 from each game.jsonl.

Options:
  -f, --fps N   Video frame rate (default: $FPS, matches run_game.py)
  -h            Show this help

Examples:
  $(basename "$0")                                    # all 270 games
  $(basename "$0") game_logs/homogeneous/gpt5.5/      # one condition
  $(basename "$0") -f 2 game_logs/heterogeneous/
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--fps) FPS="$2"; shift 2 ;;
        -h|--help) usage ;;
        -*) echo "Unknown option: $1"; usage ;;
        *)  LOG_ROOT="$1"; shift ;;
    esac
done

if ! command -v ffmpeg &>/dev/null; then
    echo "ERROR: ffmpeg is not installed."
    exit 1
fi

if [ ! -d "$LOG_ROOT" ]; then
    echo "ERROR: directory not found: $LOG_ROOT"
    exit 1
fi

# Count first so we can show [i/total] progress.
total=$(find "$LOG_ROOT" -name game.jsonl | wc -l | tr -d ' ')
if [ "$total" -eq 0 ]; then
    echo "No game.jsonl files found under $LOG_ROOT"
    exit 0
fi

echo "╔══════════════════════════════════════════════╗"
echo "║      QUACK Batch Replay                      ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Log root:  $LOG_ROOT"
echo "║  Games:     $total"
echo "║  FPS:       $FPS"
echo "╚══════════════════════════════════════════════╝"
echo ""

START_TIME=$(date +%s)
i=0
ok=0
fail=0
FAILED_LOGS=()

# Read all log paths into an array FIRST. Do NOT run python/ffmpeg inside
# ``while read; do ... done < <(find ...)`` — child processes inherit the
# same stdin (the find pipe). ffmpeg reads stdin by default and will
# consume bytes from the *next* path line, truncating ``game_logs`` →
# ``e_logs`` (exactly 3 bytes = "gam").
LOGS=()
while IFS= read -r line || [ -n "$line" ]; do
    line="${line//$'\r'/}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -n "$line" ] && LOGS+=("$line")
done < <(find "$LOG_ROOT" -name game.jsonl | sort)

for log in "${LOGS[@]}"; do
    i=$((i + 1))
    if [ ! -f "$log" ]; then
        fail=$((fail + 1))
        FAILED_LOGS+=("$log")
        echo "━━━ [$i/$total] MISSING game.jsonl ━━━"
        printf '    %q\n' "$log"
        echo "    ✗ skipped (file not found)"
        echo ""
        continue
    fi

    # Resolve once so replay always gets a stable absolute path.
    log="$(cd "$(dirname "$log")" && pwd)/$(basename "$log")"
    run_dir="$(dirname "$log")"
    run_name="$(basename "$run_dir")"
    pct=$(( i * 100 / total ))

    echo "━━━ [$i/$total] (${pct}%) $run_name ━━━"
    printf '    %s\n' "$log"

    game_start=$(date +%s)

    rm -rf "$run_dir/renders/god_view" "$run_dir/video.mp4"

    if python "$SCRIPT_DIR/replay_game.py" "$log" \
        -o "$run_dir/renders/god_view" \
        --video "$run_dir/video.mp4" \
        --fps "$FPS"; then
        game_elapsed=$(( $(date +%s) - game_start ))
        ok=$((ok + 1))
        echo "    ✓ done (${game_elapsed}s)"
    else
        game_elapsed=$(( $(date +%s) - game_start ))
        fail=$((fail + 1))
        FAILED_LOGS+=("$log")
        echo "    ✗ FAILED (${game_elapsed}s)"
    fi
    echo ""
done

END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
HOURS=$(( ELAPSED / 3600 ))
MINUTES=$(( (ELAPSED % 3600) / 60 ))
SECS=$(( ELAPSED % 60 ))

echo "╔══════════════════════════════════════════════╗"
echo "║      Batch replay complete                   ║"
echo "║  Elapsed: ${HOURS}h ${MINUTES}m ${SECS}s"
echo "║  OK:      $ok / $total"
echo "║  Failed:  $fail"
echo "╚══════════════════════════════════════════════╝"

if [ "$fail" -gt 0 ]; then
    echo ""
    echo "Failed logs:"
    for f in "${FAILED_LOGS[@]}"; do
        echo "  - $f"
    done
    exit 2
fi
