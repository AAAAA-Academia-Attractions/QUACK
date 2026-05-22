#!/usr/bin/env bash
# Run evaluation per experimental condition.
#
# Walks game_logs/homogeneous/* and game_logs/heterogeneous/* and
# invokes evaluate_batch.py independently for each condition dir.
# Per-condition runs are isolated: a failure in one (e.g. an API
# hiccup on Tier 3) does not abort the others, and each condition's
# aggregated output lands in its own ``evaluation/`` directory next
# to the games.
#
# Usage:
#   ./scripts/batch_evaluate.sh                             # all 9 conditions, Tier 1 + 2 only
#   ./scripts/batch_evaluate.sh --tier3                     # include Tier 3 (uses api_key.txt)
#   ./scripts/batch_evaluate.sh --tier3 --model gpt-5.5     # explicit Tier 3 extraction model
#   ./scripts/batch_evaluate.sh -c homogeneous              # only homogeneous conditions
#   ./scripts/batch_evaluate.sh -c heterogeneous --tier3    # only heterogeneous conditions
#   ./scripts/batch_evaluate.sh -d game_logs_archive --tier3  # custom log root
set -uo pipefail  # NOT -e: we want to continue after a condition fails

LOG_ROOT="game_logs"
CATEGORIES="homogeneous heterogeneous"
RUN_TIER3=false
MODEL="gpt-5.5"
EXTRA_ARGS=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [-- EXTRA_ARGS_TO_EVALUATE_BATCH...]

Runs ``evaluate_batch.py`` once per experimental condition
(``<log-root>/<category>/<condition>/``). One condition failure
does not abort the others — each condition is summarised at the
end.

Options:
  -d DIR         Log root (default: $LOG_ROOT)
  -c CATEGORY    Only ``homogeneous`` or ``heterogeneous``
                 (default: both)
  --tier3        Enable Tier 3 statement verification (requires API key,
                 reads api_key.txt if --api-key is not passed)
  --model NAME   Tier 3 LLM model (default: $MODEL; only used with --tier3)
  -h             Show this help

Examples:
  $(basename "$0")                          # Tier 1 + 2 for all 9 conditions
  $(basename "$0") --tier3                  # full pipeline incl. Tier 3
  $(basename "$0") -c homogeneous --tier3   # only homogeneous, full pipeline
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -d)        LOG_ROOT="$2"; shift 2 ;;
        -c)        CATEGORIES="$2"; shift 2 ;;
        --tier3)   RUN_TIER3=true; shift ;;
        --model)   MODEL="$2"; shift 2 ;;
        -h)        usage ;;
        --)        shift; EXTRA_ARGS="$*"; break ;;
        *)         EXTRA_ARGS="$EXTRA_ARGS $1"; shift ;;
    esac
done

if [ ! -d "$LOG_ROOT" ]; then
    echo "ERROR: Log root '$LOG_ROOT' does not exist."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL_SCRIPT="$SCRIPT_DIR/evaluate_batch.py"

# Collect condition directories.
CONDITIONS=()
for category in $CATEGORIES; do
    category_dir="$LOG_ROOT/$category"
    if [ ! -d "$category_dir" ]; then
        echo "WARNING: skipping missing category dir: $category_dir"
        continue
    fi
    for cond_dir in "$category_dir"/*/; do
        [ -d "$cond_dir" ] || continue
        CONDITIONS+=("${cond_dir%/}")
    done
done

if [ ${#CONDITIONS[@]} -eq 0 ]; then
    echo "No conditions found under $LOG_ROOT/{$CATEGORIES}/"
    exit 1
fi

echo "╔══════════════════════════════════════════════╗"
echo "║      QUACK Batch Evaluation                  ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Log root:    $LOG_ROOT"
echo "║  Categories:  $CATEGORIES"
echo "║  Conditions:  ${#CONDITIONS[@]}"
echo "║  Tier 3:      $RUN_TIER3"
if [ "$RUN_TIER3" = true ]; then
    echo "║  Model:       $MODEL"
fi
echo "╚══════════════════════════════════════════════╝"
echo ""

# Build the trailing flag list once.
EVAL_FLAGS=()
if [ "$RUN_TIER3" = true ]; then
    EVAL_FLAGS+=("--tier3" "--model" "$MODEL")
fi

START_TIME=$(date +%s)
PASSED=()
FAILED=()
i=0
for cond_dir in "${CONDITIONS[@]}"; do
    i=$((i + 1))
    cond_label="${cond_dir#"$LOG_ROOT"/}"
    echo "━━━ [$i/${#CONDITIONS[@]}] Evaluating: $cond_label ━━━"
    if python "$EVAL_SCRIPT" "$cond_dir" "${EVAL_FLAGS[@]}" $EXTRA_ARGS; then
        PASSED+=("$cond_label")
    else
        echo "  (condition '$cond_label' failed; continuing with the rest)"
        FAILED+=("$cond_label")
    fi
    echo ""
done

END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
HOURS=$(( ELAPSED / 3600 ))
MINUTES=$(( (ELAPSED % 3600) / 60 ))
SECS=$(( ELAPSED % 60 ))

echo "╔══════════════════════════════════════════════╗"
echo "║      Batch evaluation complete               ║"
echo "║  Elapsed: ${HOURS}h ${MINUTES}m ${SECS}s"
echo "║  Passed:  ${#PASSED[@]} / ${#CONDITIONS[@]}"
echo "║  Failed:  ${#FAILED[@]}"
echo "╚══════════════════════════════════════════════╝"
if [ ${#FAILED[@]} -gt 0 ]; then
    echo ""
    echo "Failed conditions:"
    for c in "${FAILED[@]}"; do
        echo "  - $c"
    done
    exit 2
fi
