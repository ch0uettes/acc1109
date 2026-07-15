from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from app.balance.constraints import HardConstraintLayer
from app.balance.strategy import STRATEGY_REGISTRY
from app.models.server_membership import ServerMembership
from app.position.schemas import RolePreference
from app.position.signup import PlayerSignup
from app.services.player_service import PlayerService
from app.services.rbac import Permission, has_permission
from app.services.server_service import ServerService
from app.services.team_service import TeamService
from app.utils.enums import Position
from app.utils.exceptions import AppError, InvalidPlayerCountError

NO_SUB_ROLE = "없음"

BREAKDOWN_LABELS = {
    "mean_balance": "전체 평균 균형",
    "outlier_penalty": "극단 팀 페널티",
    "team_variance": "팀 내부 안정성",
    "role_penalty": "포지션 페널티",
    "lane_balance": "라인별 격차 (RMS)",
    "tier_distribution": "티어 분포 격차",
    "internal_rating": "내전 전용 Rating 격차 (신뢰도 보정)",
}

STRATEGY_LABELS = {
    "competitive": "Competitive - 라인전 공정성 최우선",
    "comfort": "Comfort - 원하는 포지션 최우선",
    "stable": "Stable (기본) - 전체 안정성 최우선",
}


def render(session: Session, server_id: int, actor: ServerMembership) -> None:
    st.header("팀 생성")
    player_service = PlayerService(session, server_id)

    strategy_key = st.selectbox(
        "밸런싱 전략",
        list(STRATEGY_LABELS.keys()),
        index=list(STRATEGY_LABELS.keys()).index("stable"),
        format_func=lambda k: STRATEGY_LABELS[k],
    )
    server = ServerService(session).get_server(server_id)
    team_service = TeamService(
        session,
        server_id,
        strategy=STRATEGY_REGISTRY[strategy_key](),
        normalization_config=server.normalization_config if server else None,
        hard_constraints=HardConstraintLayer(server.hard_constraint_config) if server else None,
    )

    players = player_service.list_players()
    options = {f"{p.nickname} ({p.tier.value})": p for p in players}
    selected_labels = st.multiselect("참가자 선택 (5명 단위)", list(options.keys()))
    selected = [options[label] for label in selected_labels]

    overrides = _render_match_overrides(selected)
    top_n = st.slider("추천 조합 개수", min_value=3, max_value=5, value=3)

    if st.button("팀 생성", disabled=len(selected) == 0):
        signups = [PlayerSignup(player=p, match_override=overrides.get(p.id)) for p in selected]
        try:
            results = team_service.generate_top_teams(signups, k=top_n)
        except InvalidPlayerCountError as exc:
            st.error(str(exc))
        else:
            # Snapshot signups/strategy alongside results - the strategy
            # dropdown or player selection could change on a later rerun
            # (e.g. right before saving), and the decision log must
            # reflect what actually PRODUCED these results, not whatever
            # the widgets happen to show at save time.
            st.session_state["last_balance_results"] = results
            st.session_state["last_signups"] = signups
            st.session_state["last_strategy_key"] = strategy_key

    results = st.session_state.get("last_balance_results")
    if not results:
        return

    used_strategy_key = st.session_state.get("last_strategy_key", strategy_key)
    st.caption(f"밸런싱 전략: {STRATEGY_LABELS[used_strategy_key]} · 상위 {len(results)}개 조합")

    labels = [f"조합 {i + 1}위 (cost {r.cost:.1f})" for i, r in enumerate(results)]
    tabs = st.tabs(labels)
    for tab, result in zip(tabs, results):
        with tab:
            _render_combo(result)

    if not has_permission(actor.role, Permission.CREATE_MATCH):
        st.caption("팀 저장은 Server Admin 이상만 가능합니다.")
        return

    save_label = st.selectbox("저장할 조합 선택", labels)
    save_reason = st.text_input("선택 사유 (선택) - AI 1위와 다른 조합을 고른 경우 특히 남겨두면 좋습니다", key="save_reason")
    if st.button("팀 저장"):
        chosen_rank = labels.index(save_label)
        chosen = results[chosen_rank]
        try:
            team_service.save_generated_teams(chosen, actor.role)
        except AppError as exc:
            st.error(str(exc))
        else:
            signups = st.session_state.get("last_signups", [])
            team_service.log_decision(
                signups,
                used_strategy_key,
                results,
                chosen_rank=chosen_rank + 1,
                reason=save_reason or None,
            )
            st.success(f"'{save_label}' 조합을 저장했습니다.")


def _render_combo(result) -> None:
    st.caption(f"총 점수 (cost) = {result.cost:.3f}")
    if result.contributions:
        with st.expander("Feature별 기여도 (Raw → Normalized → Weight → Contribution)", expanded=False):
            st.dataframe(
                [
                    {
                        "Feature": BREAKDOWN_LABELS.get(c.name, c.name),
                        "Raw": round(c.raw, 2),
                        "Normalized": round(c.normalized, 3),
                        "Weight": c.weight,
                        "Contribution": round(c.contribution, 4),
                        "기여도": f"{c.contribution_pct:.0f}%",
                    }
                    for c in result.contributions
                ],
                use_container_width=True,
                hide_index=True,
            )

    columns = st.columns(len(result.teams))
    for col, team in zip(columns, result.teams):
        with col:
            st.subheader(f"{team.index + 1}팀 (평균 {team.average_rating:.0f})")
            if team.slots is not None:
                for slot in sorted(team.slots, key=lambda s: list(Position).index(s.position)):
                    penalty_note = (
                        f" [{slot.role_source}, +{slot.role_penalty:.0f}]" if slot.role_penalty else ""
                    )
                    st.write(
                        f"- {slot.position.value}: {slot.player.nickname} "
                        f"({slot.player.tier.value}){penalty_note}"
                    )
            else:
                for player in team.players:
                    st.write(
                        f"- {player.nickname} ({team.position_for(player.id).value}, {player.tier.value})"
                    )


def _render_match_overrides(selected: list) -> dict[int, RolePreference]:
    """Optional this-match-only Main/Sub override per selected player -
    never touches the Player's Profile, only affects this one balancer
    run (see RolePreferenceManager's priority order)."""
    overrides: dict[int, RolePreference] = {}
    if not selected:
        return overrides

    with st.expander("이번 내전 전용 포지션 (선택)"):
        st.caption("체크하지 않으면 프로필의 주/부 포지션이 그대로 사용됩니다.")
        for player in selected:
            use_override = st.checkbox(
                f"{player.nickname} - 이번 경기만 다른 포지션", key=f"override_toggle_{player.id}"
            )
            if not use_override:
                continue
            ocol1, ocol2 = st.columns(2)
            override_main = ocol1.selectbox(
                "이번 경기 주 포지션", list(Position), key=f"override_main_{player.id}"
            )
            sub_choice = ocol2.selectbox(
                "이번 경기 부 포지션 (선택)",
                [NO_SUB_ROLE, *list(Position)],
                key=f"override_sub_{player.id}",
                format_func=lambda x: x if x == NO_SUB_ROLE else x.value,
            )
            overrides[player.id] = RolePreference(
                main=override_main, sub=None if sub_choice == NO_SUB_ROLE else sub_choice
            )

    return overrides
