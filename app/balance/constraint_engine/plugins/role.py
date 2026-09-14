from __future__ import annotations

from types import MappingProxyType

from app.balance.constraint_engine.base import LeafHardConstraint, PartialHardConstraint
from app.balance.constraint_engine.context import ConstraintContext
from app.balance.constraint_engine.result import ConstraintPipeline, ConstraintResult, ConstraintStatus


class FixedRoleConstraint(LeafHardConstraint):
    """The one genuinely new capability this pass ships. Today a this-match
    RolePreference override (see PlayerSignup.match_override) is only a
    soft nudge - RolePreferenceManager.resolve() makes it that player's
    "main" for scoring purposes, but nothing rejects a candidate that
    fails to actually grant it (with enough other players, the search can
    still place an overridden player elsewhere at a higher, but not
    infinite, cost). This constraint makes "operator pinned this player to
    this position for this match" an actual hard requirement: any
    candidate where an overridden player's TeamSlot.role_source != "main"
    is rejected outright.

    Only fires for player ids in context.override_player_ids (populated
    from PlayerSignup.match_override, not from a player's ordinary
    profile main/sub role) - see ConstraintContext.override_player_ids
    for why that distinction can't be recovered from role_preferences
    alone."""

    name = "fixed_role"
    pipeline = ConstraintPipeline.ROLE
    default_priority = 85
    description = "운영자가 이번 경기에 고정한 포지션은 반드시 배정되어야 합니다"

    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        if not context.override_player_ids:
            return ConstraintResult(
                constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
                status=ConstraintStatus.PASS, priority=self.default_priority,
            )
        for team in context.teams or ():
            if team.slots is None:
                continue
            for slot in team.slots:
                if slot.player.id in context.override_player_ids and slot.role_source != "main":
                    return ConstraintResult(
                        constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
                        status=ConstraintStatus.FAIL, priority=self.default_priority,
                        reason=f"{slot.player.nickname}이(가) 고정된 포지션을 배정받지 못했습니다 "
                        f"(배정: {slot.position.value}, 실제 배정 근거: {slot.role_source})",
                        metadata=MappingProxyType(
                            {"player_id": slot.player.id, "assigned_position": slot.position.value}
                        ),
                    )
        return ConstraintResult(
            constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
            status=ConstraintStatus.PASS, priority=self.default_priority,
        )


class FixedRoleCollisionConstraint(PartialHardConstraint):
    """Prunes a branch the moment it would seat two hard-forced ('이번
    경기 고정') players onto the same roster for the same forced
    Position - without this, FixedRoleConstraint (the LEAF_HARD sibling
    above) can only reject a candidate after a *complete* team is built,
    so a colliding pair (e.g. two players both forced to JUNGLE on the
    same match) makes the DFS spend its entire node/time budget
    exploring leaves that were always doomed, then silently fall back to
    the warm-start result - which is just as likely to violate the same
    override, returned with no indication the operator's pin wasn't
    honored.

    Monotonic by construction: once two forced-same-position players
    share a roster, no further placement can undo that, so it's safe to
    prune here rather than waiting for a leaf."""

    name = "fixed_role_collision"
    pipeline = ConstraintPipeline.ROLE
    default_priority = 85
    description = "고정 포지션이 겹치는 두 참가자가 같은 팀에 배치되지 않도록 미리 차단합니다"

    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        candidate = context.candidate_player
        if candidate is None or context.team_index is None or candidate.id not in context.override_player_ids:
            return ConstraintResult(
                constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
                status=ConstraintStatus.PASS, priority=self.default_priority,
            )
        candidate_position = context.role_preferences[candidate.id].main
        roster = context.rosters[context.team_index] if context.team_index < len(context.rosters) else ()
        for teammate in roster:
            if (
                teammate.id in context.override_player_ids
                and context.role_preferences[teammate.id].main == candidate_position
            ):
                return ConstraintResult(
                    constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
                    status=ConstraintStatus.FAIL, priority=self.default_priority,
                    reason=(
                        f"{candidate.nickname}과(와) {teammate.nickname}이(가) 같은 팀에서 "
                        f"동일한 고정 포지션({candidate_position.value})을 두고 충돌합니다"
                    ),
                    prune=True,
                )
        return ConstraintResult(
            constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
            status=ConstraintStatus.PASS, priority=self.default_priority,
        )
