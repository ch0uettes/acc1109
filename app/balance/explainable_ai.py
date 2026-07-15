from __future__ import annotations

import dataclasses

from app.balance.execution_context import ExecutionContext, ExplainData

DEFAULT_TOP_N = 3


class ExplainableAI:
    """Reads runtime.feature_snapshots (the single source of truth for
    Feature results, populated by BalanceEvaluator via the search stage -
    see execution_context.py) and runtime.constraint_result_details (the
    Constraint Engine's raw per-candidate output) and turns both into
    result.explain_data, a smaller human/UI-facing summary. Never
    recomputes a Feature score or re-runs a Constraint plugin itself -
    that would duplicate BalanceEvaluator's/ConstraintExecutor's job and
    risk disagreeing with the number that actually decided the search."""

    def __init__(self, top_n: int = DEFAULT_TOP_N) -> None:
        self.top_n = top_n

    def explain(self, context: ExecutionContext) -> ExecutionContext:
        top_contributors = {
            index: sorted(contributions, key=lambda c: abs(c.contribution), reverse=True)[: self.top_n]
            for index, contributions in context.runtime.feature_snapshots.items()
        }
        new_result = dataclasses.replace(
            context.result,
            top_recommendations=context.runtime.candidate_teams,
            explain_data=ExplainData(
                top_contributors=top_contributors,
                constraint_summary=dict(context.runtime.constraint_result_details),
            ),
        )
        return dataclasses.replace(context, result=new_result)
