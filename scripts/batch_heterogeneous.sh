#!/usr/bin/env bash
# Run N heterogeneous games for specified goose/duck model pairs.
#
# Usage:
#   ./scripts/batch_heterogeneous.sh                                       # all pairs, 50 seeds
#   ./scripts/batch_heterogeneous.sh -g gpt5.4 -d claude_opus4.6          # single pair
#   ./scripts/batch_heterogeneous.sh -g gpt5.4 -d claude_opus4.6 -n 10    # 10 games
#   ./scripts/batch_heterogeneous.sh -g gpt5.4 -d all -n 5                # gpt5.4 geese vs every duck
set -euo pipefail

ALL_MODELS="gpt5.2 gpt5.4 gemini3.1pro claude_opus4.6 grok4 kimi2.5"
NUM_GAMES=50
START_SEED=1
GOOSE_MODELS=""
DUCK_MODELS=""
EXTRA_ARGS=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [-- EXTRA_HYDRA_ARGS...]

Options:
  -g MODELS   Comma-separated goose model(s) (default: all)
  -d MODELS   Comma-separated duck model(s), or "all" (default: all)
  -n NUM      Number of games per pair (default: $NUM_GAMES)
  -s START    Starting seed (default: $START_SEED)
  -h          Show this help

Pairs where goose == duck are skipped (use batch_homogeneous.sh instead).

Examples:
  $(basename "$0")                                           # all cross-model pairs × 50 seeds
  $(basename "$0") -g gpt5.4 -d claude_opus4.6 -n 10        # single pair × 10
  $(basename "$0") -g gpt5.4 -d all -n 5                    # gpt5.4 geese vs all ducks × 5
  $(basename "$0") -g gpt5.4,grok4 -d claude_opus4.6 -n 5   # 2 goose models vs 1 duck × 5
EOF
    exit 0
}

while getopts "g:d:n:s:h" opt; do
    case $opt in
        g) GOOSE_MODELS="${OPTARG//,/ }" ;;
        d) DUCK_MODELS="${OPTARG//,/ }" ;;
        n) NUM_GAMES="$OPTARG" ;;
        s) START_SEED="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done
shift $((OPTIND - 1))
EXTRA_ARGS="$*"

[ -z "$GOOSE_MODELS" ] && GOOSE_MODELS="$ALL_MODELS"
[ -z "$DUCK_MODELS" ] || [ "$DUCK_MODELS" = "all" ] && DUCK_MODELS="$ALL_MODELS"

END_SEED=$((START_SEED + NUM_GAMES - 1))
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Count pairs (excluding same-model)
num_pairs=0
for g in $GOOSE_MODELS; do
    for d in $DUCK_MODELS; do
        [ "$g" = "$d" ] && continue
        num_pairs=$((num_pairs + 1))
    done
done

echo "============================================"
echo "  QUACK Heterogeneous Batch Runner"
echo "============================================"
echo "Goose models: $GOOSE_MODELS"
echo "Duck models:  $DUCK_MODELS"
echo "Pairs:        $num_pairs (same-model pairs skipped)"
echo "Seeds:        $START_SEED .. $END_SEED ($NUM_GAMES games each)"
[ -n "$EXTRA_ARGS" ] && echo "Extra args:   $EXTRA_ARGS"
echo "--------------------------------------------"

total=0
failed=0

for goose_model in $GOOSE_MODELS; do
    for duck_model in $DUCK_MODELS; do
        [ "$goose_model" = "$duck_model" ] && continue

        echo ""
        echo ">>> Geese: $goose_model  |  Duck: $duck_model"
        for seed in $(seq "$START_SEED" "$END_SEED"); do
            total=$((total + 1))
            echo -n "  [geese_${goose_model}_duck_${duck_model}] seed=${seed} ... "
            if python "$SCRIPT_DIR/run_game.py" \
                experiment=heterogeneous \
                model="$goose_model" \
                experiment.duck_model="$duck_model" \
                seed="$seed" $EXTRA_ARGS \
                > /dev/null 2>&1; then
                echo "OK"
            else
                echo "FAILED"
                failed=$((failed + 1))
            fi
        done
    done
done

echo ""
echo "============================================"
echo "  Done: $((total - failed))/$total succeeded"
[ "$failed" -gt 0 ] && echo "  $failed game(s) failed"
echo "============================================"
