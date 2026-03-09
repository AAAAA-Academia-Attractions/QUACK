#!/usr/bin/env bash
# Run the full QUACK experiment suite: homogeneous + heterogeneous + evaluation.
#
# Usage:
#   ./scripts/batch_full_experiment.sh              # 50 games per condition (default)
#   ./scripts/batch_full_experiment.sh -n 10         # 10 games per condition (quick test)
#   ./scripts/batch_full_experiment.sh -n 5 --eval   # 5 games + run evaluation after
set -euo pipefail

NUM_GAMES=50
START_SEED=1
RUN_EVAL=false
EXTRA_ARGS=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [-- EXTRA_HYDRA_ARGS...]

Runs the full experiment matrix:
  - 5 homogeneous conditions  (one per model)
  - 20 heterogeneous conditions (all cross-model pairs)
  Total: 25 conditions × N games each

Options:
  -n NUM      Number of games per condition (default: $NUM_GAMES)
  -s START    Starting seed (default: $START_SEED)
  --eval      Run batch evaluation after all games finish
  -h          Show this help

Examples:
  $(basename "$0")                  # full experiment: 25 × 50 = 1250 games
  $(basename "$0") -n 5            # quick test: 25 × 5 = 125 games
  $(basename "$0") -n 10 --eval    # 250 games + evaluation
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -n)      NUM_GAMES="$2"; shift 2 ;;
        -s)      START_SEED="$2"; shift 2 ;;
        --eval)  RUN_EVAL=true; shift ;;
        -h)      usage ;;
        --)      shift; EXTRA_ARGS="$*"; break ;;
        *)       EXTRA_ARGS="$EXTRA_ARGS $1"; shift ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
START_TIME=$(date +%s)

echo "╔══════════════════════════════════════════════╗"
echo "║      QUACK Full Experiment Suite             ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Games per condition: $NUM_GAMES"
echo "║  Starting seed:      $START_SEED"
echo "║  Run evaluation:     $RUN_EVAL"
echo "╚══════════════════════════════════════════════╝"
echo ""

# --- Phase 1: Homogeneous ---
echo "━━━ Phase 1/3: Homogeneous experiments ━━━"
bash "$SCRIPT_DIR/batch_homogeneous.sh" -n "$NUM_GAMES" -s "$START_SEED" $EXTRA_ARGS

# --- Phase 2: Heterogeneous ---
echo ""
echo "━━━ Phase 2/3: Heterogeneous experiments ━━━"
bash "$SCRIPT_DIR/batch_heterogeneous.sh" -n "$NUM_GAMES" -s "$START_SEED" $EXTRA_ARGS

# --- Phase 3: Evaluation ---
if [ "$RUN_EVAL" = true ]; then
    echo ""
    echo "━━━ Phase 3/3: Batch evaluation ━━━"
    python "$SCRIPT_DIR/evaluate_batch.py" game_logs/
else
    echo ""
    echo "━━━ Phase 3/3: Evaluation skipped (use --eval to enable) ━━━"
fi

END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
HOURS=$(( ELAPSED / 3600 ))
MINUTES=$(( (ELAPSED % 3600) / 60 ))
SECONDS=$(( ELAPSED % 60 ))

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Experiment complete                         ║"
echo "║  Elapsed: ${HOURS}h ${MINUTES}m ${SECONDS}s"
echo "╚══════════════════════════════════════════════╝"
