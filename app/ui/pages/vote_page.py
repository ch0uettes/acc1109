from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from app.models.server_membership import ServerMembership
from app.services.match_service import MatchService
from app.services.player_service import PlayerService
from app.services.vote_service import VoteService
from app.utils.exceptions import PermissionDeniedError


def render(session: Session, server_id: int, actor: ServerMembership) -> None:
    st.header("User MVP 투표")

    match_service = MatchService(session, server_id)
    pending = match_service.list_pending_votes()
    if not pending:
        st.info("투표 대기 중인 경기가 없습니다.")
        return

    players_by_id = {p.id: p for p in PlayerService(session, server_id).list_players()}

    def _match_label(m) -> str:
        ai_mvp = players_by_id.get(m.ai_mvp_player_id)
        ai_mvp_name = ai_mvp.nickname if ai_mvp else "?"
        return f"#{m.id} ({m.played_at:%Y-%m-%d %H:%M}) - AI MVP: {ai_mvp_name}"

    match_options = {_match_label(m): m for m in pending}
    match_label = st.selectbox("투표할 경기 선택", list(match_options.keys()))
    match = match_options[match_label]

    candidate_names = {
        players_by_id[p.player_id].nickname: p.player_id
        for p in match.participants
        if p.player_id in players_by_id
    }

    vote_service = VoteService(session, server_id)

    with st.form("cast_vote"):
        voter_label = st.selectbox("투표자", list(candidate_names.keys()))
        voted_label = st.selectbox("MVP로 투표할 선수", list(candidate_names.keys()))
        submitted = st.form_submit_button("투표하기")

        if submitted:
            vote_service.cast_vote(
                match_id=match.id,
                voter_player_id=candidate_names[voter_label],
                voted_player_id=candidate_names[voted_label],
            )
            st.success("투표 완료")
            st.rerun()

    st.subheader("현재 집계")
    leading_player_id = vote_service.tally_user_mvp(match.id)
    if leading_player_id is None:
        st.write("아직 투표가 없습니다.")
    else:
        st.write(f"현재 1위: **{players_by_id[leading_player_id].nickname}**")

        if st.button("투표 마감 및 User MVP 확정"):
            try:
                match_service.set_user_mvp(match.id, leading_player_id, actor_role=actor.role)
            except PermissionDeniedError as exc:
                st.error(f"권한이 없습니다: {exc}")
            else:
                st.success(f"User MVP를 {players_by_id[leading_player_id].nickname}(으)로 확정했습니다.")
                st.rerun()
