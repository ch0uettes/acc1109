from __future__ import annotations

from app.balance.constraint_engine.base import LeafHardConstraint
from app.balance.constraint_engine.context import ConstraintContext
from app.balance.constraint_engine.result import ConstraintPipeline, ConstraintResult, ConstraintStatus
from app.utils.enums import Position

TEAM_SIZE = 5

"""Structural pipeline: re-homes HardConstraintLayer._is_structurally_valid's
logic (app/balance/constraints.py) into named LeafHardConstraint plugins.
Provably inert defense-in-depth - the DFS's own branching (only ever
appends one not-yet-placed player to a not-yet-full team) and
PositionAssigner's complete-bijection guarantee already make these
invariants impossible to violate. They exist so the Explainable output
can genuinely say "모든 Hard Constraint 만족" itemized by name, and so a
future non-DFS SearchEngine implementation gets the same safety net for
free by registering against this same ConstraintRegistry."""


class TeamSizeConstraint(LeafHardConstraint):
    name = "team_size"
    pipeline = ConstraintPipeline.STRUCTURAL
    default_priority = 100
    description = "팀 인원은 정확히 5명이어야 합니다"

    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        for team in context.teams or ():
            if len(team.players) != TEAM_SIZE:
                return ConstraintResult(
                    constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
                    status=ConstraintStatus.FAIL, priority=self.default_priority,
                    reason=f"{team.index}번 팀 인원이 {len(team.players)}명입니다 (정확히 {TEAM_SIZE}명 필요)",
                )
        return ConstraintResult(
            constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
            status=ConstraintStatus.PASS, priority=self.default_priority,
        )


class UniquePlayerConstraint(LeafHardConstraint):
    name = "unique_player"
    pipeline = ConstraintPipeline.STRUCTURAL
    default_priority = 95
    description = "동일 플레이어가 두 팀 이상에 속할 수 없습니다"

    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        seen: set[int] = set()
        for team in context.teams or ():
            for player in team.players:
                if player.id in seen:
                    return ConstraintResult(
                        constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
                        status=ConstraintStatus.FAIL, priority=self.default_priority,
                        reason=f"{player.nickname}가 두 팀 이상에 배정되었습니다",
                    )
                seen.add(player.id)
        return ConstraintResult(
            constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
            status=ConstraintStatus.PASS, priority=self.default_priority,
        )


class RequiredRoleConstraint(LeafHardConstraint):
    name = "required_role"
    pipeline = ConstraintPipeline.STRUCTURAL
    default_priority = 90
    description = "각 팀은 5개 포지션을 정확히 하나씩 충족해야 합니다"

    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        for team in context.teams or ():
            if team.slots is not None and {slot.position for slot in team.slots} != set(Position):
                return ConstraintResult(
                    constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
                    status=ConstraintStatus.FAIL, priority=self.default_priority,
                    reason=f"{team.index}번 팀이 5개 포지션을 모두 충족하지 못했습니다",
                )
        return ConstraintResult(
            constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
            status=ConstraintStatus.PASS, priority=self.default_priority,
        )
