from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from app.models.server_membership import ServerMembership
from app.services.stats_service import StatsService


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
