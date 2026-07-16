from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from app.balance.config import HardConstraintConfig, NormalizationConfig
from app.balance.constraint_engine import DEFAULT_CONSTRAINT_REGISTRY, ConstraintPipeline, ConstraintTier
from app.models.server_membership import ServerMembership
from app.services.rbac import Permission, has_permission
from app.services.server_service import ServerService
from app.utils.enums import Role
from app.utils.exceptions import AppError

ROLE_LABEL = {
    Role.PLATFORM_ADMIN: "Platform Admin",
    Role.OWNER: "Owner",
    Role.SERVER_ADMIN: "Server Admin",
    Role.MODERATOR: "Moderator",
    Role.PLAYER: "Player",
}

CONSTRAINT_TIER_LABEL = {
    ConstraintTier.PARTIAL_HARD: "Partial-Hard (탐색 중 가지치기)",
    ConstraintTier.LEAF_HARD: "Leaf-Hard (완성된 팀 검증)",
    ConstraintTier.SOFT: "Soft (탐색 순서 힌트)",
    ConstraintTier.PREFERENCE: "Preference (운영 정책)",
}

CONSTRAINT_PIPELINE_LABEL = {
    ConstraintPipeline.STRUCTURAL: "Structural (팀 구성 무결성)",
    ConstraintPipeline.ROLE: "Role (포지션 규칙)",
    ConstraintPipeline.RELATIONSHIP: "Relationship (듀오/분리)",
    ConstraintPipeline.PREFERENCE: "Preference (대회/서버 정책)",
    ConstraintPipeline.SEARCH_GUIDANCE: "Search Guidance (탐색 힌트)",
}


def render(session: Session, server_id: int, actor: ServerMembership) -> None:
    st.header("서버 관리")
    service = ServerService(session)

    st.subheader("멤버 목록")
    members = service.list_members(server_id)
    st.dataframe(
        [{"이름": m.display_name, "역할": ROLE_LABEL[m.role]} for m in members],
        use_container_width=True,
    )

    if has_permission(actor.role, Permission.PROMOTE_TO_SERVER_ADMIN):
        _render_promote(service, server_id, actor, members)

    if has_permission(actor.role, Permission.REMOVE_SERVER_ADMIN):
        _render_demote(service, server_id, actor, members)

    if has_permission(actor.role, Permission.TRANSFER_OWNERSHIP):
        _render_transfer_ownership(service, server_id, actor, members)

    if has_permission(actor.role, Permission.MANAGE_SERVER_SETTINGS):
        _render_season_label(service, server_id, actor)
        _render_balance_config(service, server_id, actor)
        _render_constraint_priorities(service, server_id, actor)

    st.subheader("역할 변경 이력 (Audit Log)")
    history = service.role_change_history(server_id)
    if not history:
        st.info("아직 역할 변경 이력이 없습니다.")
        return

    st.dataframe(
        [
            {
                "시각": h.changed_at,
                "대상": h.target_display_name,
                "이전 역할": ROLE_LABEL[h.old_role] if h.old_role else "-",
                "변경 후 역할": ROLE_LABEL[h.new_role],
                "변경자": h.changed_by,
                "사유": h.reason or "",
            }
            for h in reversed(history)
        ],
        use_container_width=True,
    )


def _render_promote(
    service: ServerService, server_id: int, actor: ServerMembership, members: list[ServerMembership]
) -> None:
    st.subheader("멤버 승급 (Server Admin)")
    candidates = [m.display_name for m in members if m.role == Role.PLAYER]
    with st.form("promote_form"):
        if candidates:
            target = st.selectbox("대상 (Player)", candidates)
        else:
            target = st.text_input("대상 이름 (아직 등록되지 않은 이름도 가능 - Player로 자동 등록 후 승급됩니다)")
        reason = st.text_input("사유 (선택)", key="promote_reason")
        submitted = st.form_submit_button("Server Admin으로 승급")

        if submitted and target:
            try:
                service.promote_to_server_admin(server_id, actor.display_name, target, reason or None)
            except AppError as exc:
                st.error(str(exc))
            else:
                st.success(f"{target}을(를) Server Admin으로 승급했습니다.")
                st.rerun()


def _render_demote(
    service: ServerService, server_id: int, actor: ServerMembership, members: list[ServerMembership]
) -> None:
    st.subheader("Server Admin 강등")
    candidates = [m.display_name for m in members if m.role == Role.SERVER_ADMIN]
    if not candidates:
        st.caption("강등할 수 있는 Server Admin이 없습니다.")
        return

    with st.form("demote_form"):
        target = st.selectbox("대상 (Server Admin)", candidates)
        reason = st.text_input("사유 (선택)", key="demote_reason")
        submitted = st.form_submit_button("Player로 강등")

        if submitted:
            try:
                service.remove_server_admin(server_id, actor.display_name, target, reason or None)
            except AppError as exc:
                st.error(str(exc))
            else:
                st.success(f"{target}을(를) Player로 강등했습니다.")
                st.rerun()


def _render_transfer_ownership(
    service: ServerService, server_id: int, actor: ServerMembership, members: list[ServerMembership]
) -> None:
    st.subheader("Owner 이전")
    st.caption("이전 후 기존 Owner는 Server Admin이 됩니다.")
    candidates = [m.display_name for m in members if m.display_name != actor.display_name]
    if not candidates:
        st.caption("이전할 대상이 없습니다.")
        return

    with st.form("transfer_ownership_form"):
        target = st.selectbox("새 Owner", candidates)
        reason = st.text_input("사유 (선택)", key="transfer_reason")
        submitted = st.form_submit_button("Owner 이전")

        if submitted:
            try:
                service.transfer_ownership(server_id, actor.display_name, target, reason or None)
            except AppError as exc:
                st.error(str(exc))
            else:
                st.success(f"{target}에게 Owner를 이전했습니다.")
                st.rerun()


def _render_season_label(service: ServerService, server_id: int, actor: ServerMembership) -> None:
    st.subheader("현재 시즌 라벨")
    st.caption(
        "PlayerSeasonRank 기록에 붙는 메타데이터일 뿐, 밸런스 계산에는 쓰이지 않습니다. "
        "서버마다 다른 시즌/스플릿을 쓸 수 있어 서버별로 관리합니다."
    )
    server = service.get_server(server_id)
    if server is None:
        return

    with st.form("season_label_form"):
        label = st.text_input("현재 시즌 라벨", value=server.current_season_label)
        submitted = st.form_submit_button("저장")
        if submitted:
            try:
                service.update_season_label(server_id, actor.display_name, label)
            except AppError as exc:
                st.error(str(exc))
            else:
                st.success("현재 시즌 라벨을 저장했습니다.")
                st.rerun()


def _render_balance_config(service: ServerService, server_id: int, actor: ServerMembership) -> None:
    st.subheader("밸런스 계산 설정 (Feature Normalizer / Hard Constraint)")
    st.caption(
        "팀 구성 탐색에서 각 항목(평균 Rating, 라인별 격차, 팀 분산 등)을 0~1로 정규화할 때 쓰는 "
        "기준값입니다. 기본값은 이 앱의 Rating 스케일(티어당 400점)에 맞춰져 있으니, 커뮤니티의 "
        "실제 Rating 분포가 많이 다를 때만 조정하세요."
    )
    server = service.get_server(server_id)
    if server is None:
        return
    norm = server.normalization_config
    hard = server.hard_constraint_config
    breakpoints = dict(norm.tier_distribution_breakpoints)

    with st.form("balance_config_form"):
        st.markdown("**Feature Normalizer**")
        col1, col2 = st.columns(2)
        with col1:
            mean_balance_midpoint = st.number_input(
                "전체 평균 균형 - 중심점 (Logistic)", value=norm.mean_balance_midpoint, min_value=0.0, step=50.0
            )
            mean_balance_steepness = st.number_input(
                "전체 평균 균형 - 기울기",
                value=norm.mean_balance_steepness,
                min_value=0.0001,
                step=0.0005,
                format="%.4f",
            )
            outlier_penalty_midpoint = st.number_input(
                "극단 팀 페널티 - 중심점 (Logistic)", value=norm.outlier_penalty_midpoint, min_value=0.0, step=50.0
            )
            outlier_penalty_steepness = st.number_input(
                "극단 팀 페널티 - 기울기",
                value=norm.outlier_penalty_steepness,
                min_value=0.0001,
                step=0.0005,
                format="%.4f",
            )
            internal_midpoint = st.number_input(
                "내전 전용 Rating 격차 - 중심점 (Logistic)", value=norm.internal_rating_midpoint, min_value=0.0, step=50.0
            )
            internal_steepness = st.number_input(
                "내전 전용 Rating 격차 - 기울기",
                value=norm.internal_rating_steepness,
                min_value=0.0001,
                step=0.0005,
                format="%.4f",
            )
        with col2:
            lane_difference_max = st.number_input(
                "라인별 격차 상한 (Linear)", value=norm.lane_difference_max, min_value=1.0, step=100.0
            )
            team_variance_scale = st.number_input(
                "팀 내부 분산 스케일 (Logarithmic)", value=norm.team_variance_scale, min_value=1.0, step=1000.0
            )
            role_penalty_max = st.number_input(
                "포지션 페널티 상한 (Linear)", value=norm.role_penalty_max, min_value=1.0, step=50.0
            )

        st.caption("티어 분포 격차별 점수 (Piecewise) - 격차가 클수록 1.0에 가까워집니다.")
        bcols = st.columns(5)
        gap_scores = [
            bcols[0].number_input("격차 0", value=breakpoints.get(0.0, 0.0), min_value=0.0, max_value=1.0, step=0.05),
            bcols[1].number_input("격차 2", value=breakpoints.get(2.0, 0.2), min_value=0.0, max_value=1.0, step=0.05),
            bcols[2].number_input("격차 5", value=breakpoints.get(5.0, 0.5), min_value=0.0, max_value=1.0, step=0.05),
            bcols[3].number_input("격차 10", value=breakpoints.get(10.0, 0.8), min_value=0.0, max_value=1.0, step=0.05),
            bcols[4].number_input("격차 20+", value=breakpoints.get(20.0, 1.0), min_value=0.0, max_value=1.0, step=0.05),
        ]

        st.divider()
        st.markdown("**Hard Constraint (Feasibility Check)**")
        st.caption(
            "기본은 전부 비활성 - 체크한 항목만 해당 값을 초과하는 후보를 팀 구성 결과에서 제외합니다. "
            "과도하게 사용하면 경계값 근처에서 결과가 불안정해질 수 있어 권장하지 않습니다."
        )
        hcol1, hcol2 = st.columns(2)
        with hcol1:
            use_mean_balance_max = st.checkbox(
                "전체 평균 균형 상한 사용", value=hard.mean_balance_diff_max is not None
            )
            mean_balance_diff_max = st.number_input(
                "상한 값", value=hard.mean_balance_diff_max or 1000.0, min_value=0.0, step=50.0, key="mean_balance_diff_max"
            )
            use_lane_max = st.checkbox("라인별 격차 상한 사용", value=hard.lane_diff_max is not None)
            lane_diff_max = st.number_input(
                "상한 값", value=hard.lane_diff_max or 5000.0, min_value=0.0, step=100.0, key="lane_diff_max"
            )
        with hcol2:
            use_variance_max = st.checkbox("팀 내부 분산 상한 사용", value=hard.team_variance_max is not None)
            team_variance_max = st.number_input(
                "상한 값", value=hard.team_variance_max or 200_000.0, min_value=0.0, step=5000.0, key="team_variance_max"
            )
            use_main_ratio = st.checkbox("Main 포지션 최소 비율 사용", value=hard.minimum_main_role_ratio is not None)
            minimum_main_ratio = st.number_input(
                "최소 비율 (0~1)",
                value=hard.minimum_main_role_ratio or 0.6,
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                key="minimum_main_ratio",
            )

        save_col, reset_col = st.columns(2)
        submitted = save_col.form_submit_button("저장")
        reset = reset_col.form_submit_button("기본값으로 초기화")

        if submitted:
            normalization = NormalizationConfig(
                mean_balance_midpoint=mean_balance_midpoint,
                mean_balance_steepness=mean_balance_steepness,
                outlier_penalty_midpoint=outlier_penalty_midpoint,
                outlier_penalty_steepness=outlier_penalty_steepness,
                internal_rating_midpoint=internal_midpoint,
                internal_rating_steepness=internal_steepness,
                lane_difference_max=lane_difference_max,
                team_variance_scale=team_variance_scale,
                tier_distribution_breakpoints=tuple(
                    zip((0.0, 2.0, 5.0, 10.0, 20.0), gap_scores)
                ),
                role_penalty_max=role_penalty_max,
            )
            hard_constraint = HardConstraintConfig(
                mean_balance_diff_max=mean_balance_diff_max if use_mean_balance_max else None,
                lane_diff_max=lane_diff_max if use_lane_max else None,
                team_variance_max=team_variance_max if use_variance_max else None,
                minimum_main_role_ratio=minimum_main_ratio if use_main_ratio else None,
            )
            try:
                service.update_balance_config(server_id, actor.display_name, normalization, hard_constraint)
            except AppError as exc:
                st.error(str(exc))
            else:
                st.success("밸런스 설정을 저장했습니다.")
                st.rerun()

        if reset:
            try:
                service.update_balance_config(
                    server_id, actor.display_name, NormalizationConfig(), HardConstraintConfig()
                )
            except AppError as exc:
                st.error(str(exc))
            else:
                st.success("기본값으로 초기화했습니다.")
                st.rerun()


def _render_constraint_priorities(service: ServerService, server_id: int, actor: ServerMembership) -> None:
    st.subheader("Constraint 우선순위 (Search Guidance Engine)")
    st.caption(
        "팀 탐색 중 실제로 작동하는 Constraint 목록입니다. 우선순위는 같은 Tier 안에서 어느 것을 "
        "먼저 평가할지만 정합니다 - 지금 활성화된 4개는 전부 Leaf-Hard(완성된 팀을 전부 검사)라 "
        "순서를 바꿔도 통과/거부 결과 자체는 달라지지 않습니다. Soft/Preference Constraint가 "
        "추가되면 그때부터 우선순위가 탐색 순서에 실제로 영향을 줍니다."
    )
    server = service.get_server(server_id)
    if server is None:
        return

    names = DEFAULT_CONSTRAINT_REGISTRY.names()
    if not names:
        st.info("등록된 Constraint가 없습니다.")
        return

    overrides = server.constraint_priorities
    with st.form("constraint_priorities_form"):
        new_priorities: dict[str, int] = {}
        for name in names:
            constraint_cls = DEFAULT_CONSTRAINT_REGISTRY.get(name)
            current_priority = overrides.get(name, constraint_cls.default_priority)
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{name}**")
                st.caption(
                    f"{constraint_cls.description}  \n"
                    f"{CONSTRAINT_TIER_LABEL[constraint_cls.tier]} · "
                    f"{CONSTRAINT_PIPELINE_LABEL[constraint_cls.pipeline]} · "
                    f"기본 우선순위 {constraint_cls.default_priority}"
                )
            new_priorities[name] = int(
                col2.number_input(
                    "우선순위",
                    value=int(current_priority),
                    step=5,
                    key=f"constraint_priority_{name}",
                    label_visibility="collapsed",
                )
            )

        save_col, reset_col = st.columns(2)
        submitted = save_col.form_submit_button("저장")
        reset = reset_col.form_submit_button("기본값으로 초기화")

        if submitted:
            try:
                service.update_constraint_priorities(server_id, actor.display_name, new_priorities)
            except AppError as exc:
                st.error(str(exc))
            else:
                st.success("Constraint 우선순위를 저장했습니다.")
                st.rerun()

        if reset:
            try:
                service.update_constraint_priorities(server_id, actor.display_name, {})
            except AppError as exc:
                st.error(str(exc))
            else:
                st.success("기본값으로 초기화했습니다.")
                st.rerun()
