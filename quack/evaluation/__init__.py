"""QUACK Automated Evaluation Pipeline.

Provides three tiers of metrics for evaluating VLM agent performance
in the Goose Goose Duck social deduction game:

- Tier 1: Game-level metrics (outcomes, tasks, kills, meetings, ejections)
- Tier 2: Behavioral metrics (spatial, voting, task efficiency, kill patterns)
- Tier 3: Statement verification (claim extraction, ground-truth verification)
"""

from quack.evaluation.evaluator import BatchEvaluator, GameEvaluator
from quack.evaluation.log_parser import parse_log

__all__ = ["GameEvaluator", "BatchEvaluator", "parse_log"]
