from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from app.models.server_membership import ServerMembership
from app.services.stats_service import StatsService
from app.services.team_service import TeamService

STRATEGY_NAME_LABEL = {
    "competitive": "Competitive",
    "comfort": "Comfort",
    "stable": "Stable",
}


def render(session: Session, server_id: int, actor: ServerMembership) -> None:
    st.header("통계")
    service = StatsService(session, server_id)

    st.subheader("리더보드")
    leaderboard = service.leaderboard()
    if leaderboard:
        st.dataframe(
            [
                {
                    "닉네임": p.nickname,
                    "Final Rating": round(p.final_rating, 1),
                    "게임 수": p.games_played,
                }
                for p in leaderboard
            ],
            use_container_width=True,
        )
    else:
        st.info("데이터가 없습니다.")

    st.metric("AI MVP 적중률", f"{service.ai_mvp_accuracy() * 100:.1f}%")

    st.subheader("최근 팀 생성 기록 (AI Decision Log)")
    st.caption(
        "AI가 추천한 조합과 실제로 운영자가 선택한 조합을 비교합니다 - "
        "'선택'이 1위가 아니면 AI 추천을 사람이 뒤집은 경우입니다 (v2.0 학습 데이터 기반)."
    )
    decisions = TeamService(session, server_id).recent_decisions(limit=20)
    if not decisions:
        st.info("아직 저장된 팀 생성 기록이 없습니다.")
        return

    st.dataframe(
        [
            {
                "시각": d.created_at,
                "전략": STRATEGY_NAME_LABEL.get(d.strategy_name, d.strategy_name),
                "참가자 수": len(d.player_ids),
                "AI 추천 개수": len(d.recommendations),
                "선택된 순위": f"{d.chosen_rank}위" + ("" if d.chosen_rank == 1 else " (AI 1위 아님)"),
                "사유": d.reason or "",
            }
            for d in decisions
        ],
        use_container_width=True,
    )
