#!/usr/bin/env bash
# Run N homogeneous games for one or more models.
#
# Usage:
#   ./scripts/batch_homogeneous.sh                        # all models, 50 seeds
#   ./scripts/batch_homogeneous.sh -m gpt5.4              # single model
#   ./scripts/batch_homogeneous.sh -m gpt5.4 -n 10        # 10 games
#   ./scripts/batch_homogeneous.sh -m gpt5.4 -s 11 -n 10  # seeds 11-20
#   ./scripts/batch_homogeneous.sh -m gpt5.4,claude_opus4.6 -n 5
set -euo pipefail

ALL_MODELS="gpt5.2 gpt5.4 gemini3.1pro claude_opus4.6 grok4 kimi2.5"
NUM_GAMES=50
START_SEED=1
MODELS=""
EXTRA_ARGS=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [-- EXTRA_HYDRA_ARGS...]

Options:
  -m MODELS   Comma-separated model names (default: all models)
  -n NUM      Number of games per model (default: $NUM_GAMES)
  -s START    Starting seed (default: $START_SEED)
  -h          Show this help

Examples:
  $(basename "$0")                              # all 5 models × 50 seeds
  $(basename "$0") -m gpt5.4 -n 10             # GPT-5.4 × 10 seeds
  $(basename "$0") -m gpt5.4,grok4 -n 5        # two models × 5 seeds
  $(basename "$0") -m gpt5.4 -n 10 -- video=false  # pass extra Hydra args
EOF
    exit 0
}

while getopts "m:n:s:h" opt; do
    case $opt in
        m) MODELS="${OPTARG//,/ }" ;;
        n) NUM_GAMES="$OPTARG" ;;
        s) START_SEED="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done
shift $((OPTIND - 1))
EXTRA_ARGS="$*"

if [ -z "$MODELS" ]; then
    MODELS="$ALL_MODELS"
fi

END_SEED=$((START_SEED + NUM_GAMES - 1))
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "  QUACK Homogeneous Batch Runner"
echo "============================================"
echo "Models:     $MODELS"
echo "Seeds:      $START_SEED .. $END_SEED ($NUM_GAMES games each)"
[ -n "$EXTRA_ARGS" ] && echo "Extra args: $EXTRA_ARGS"
echo "--------------------------------------------"

total=0
failed=0

for model in $MODELS; do
    echo ""
    echo ">>> Model: $model"
    for seed in $(seq "$START_SEED" "$END_SEED"); do
        total=$((total + 1))
        echo -n "  [${model}] seed=${seed} ... "
        if python "$SCRIPT_DIR/run_game.py" model="$model" seed="$seed" $EXTRA_ARGS \
            > /dev/null 2>&1; then
            echo "OK"
        else
            echo "FAILED"
            failed=$((failed + 1))
        fi
    done
done

echo ""
echo "============================================"
echo "  Done: $((total - failed))/$total succeeded"
[ "$failed" -gt 0 ] && echo "  $failed game(s) failed"
echo "============================================"
