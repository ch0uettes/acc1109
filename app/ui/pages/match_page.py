from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from app.ai.contribution import OCRContributionScoreCalculator
from app.models.server_membership import ServerMembership
from app.ocr.extractor import build_ocr_extractor
from app.services.match_service import MatchService
from app.utils.exceptions import PermissionDeniedError


def render(session: Session, server_id: int, actor: ServerMembership) -> None:
    st.header("경기 저장")
    result = st.session_state.get("last_balance_result")
    if result is None:
        st.info("먼저 '팀 생성' 메뉴에서 팀을 만들어주세요.")
        return

    team_options = {f"{team.index + 1}팀": team.index for team in result.teams}
    all_players = {p.nickname: p for team in result.teams for p in team.players}

    st.subheader("결과창 스크린샷으로 자동 분석 (선택)")
    st.caption(
        "OCR로 K/D/A와 승리 팀을 최대한 읽어내지만, 해상도·클라이언트에 따라 오독할 수 있습니다. "
        "아래 표에서 반드시 확인/수정 후 저장하세요."
    )
    uploaded = st.file_uploader("결과창 스크린샷 업로드", type=["png", "jpg", "jpeg"])

    if uploaded is not None and st.button("스크린샷 분석"):
        with tempfile.NamedTemporaryFile(suffix=Path(uploaded.name).suffix, delete=False) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name

        try:
            with st.spinner("OCR 분석 중..."):
                extractor = build_ocr_extractor()
                parsed = extractor.extract(tmp_path, list(all_players.keys()))
        except NotImplementedError as exc:
            st.error(str(exc))
        else:
            st.session_state["ocr_parsed"] = parsed.model_dump()

    ocr_stats_by_player_id: dict[int, dict] = {}
    detected_winner_label = None
    parsed_state = st.session_state.get("ocr_parsed")

    if parsed_state is not None:
        st.caption(
            "선택: CS/시야점수/딜량이 담긴 상세 스탯 화면도 있으면 업로드하세요 "
            "(이름이 없어 위 표와 같은 순서로 매칭됩니다)."
        )
        detail_uploaded = st.file_uploader(
            "상세 스탯 스크린샷 업로드 (선택)", type=["png", "jpg", "jpeg"], key="detail_uploader"
        )
        if detail_uploaded is not None and st.button("상세 스탯 분석"):
            with tempfile.NamedTemporaryFile(suffix=Path(detail_uploaded.name).suffix, delete=False) as tmp:
                tmp.write(detail_uploaded.getvalue())
                detail_tmp_path = tmp.name

            try:
                with st.spinner("상세 스탯 OCR 분석 중..."):
                    extractor = build_ocr_extractor()
                    detail_stats = extractor.extract_detail_stats(detail_tmp_path)
            except NotImplementedError as exc:
                st.error(str(exc))
            else:
                # Column order in the detail screenshot isn't guaranteed to
                # match the scoreboard's row order, so join on the K/D/A
                # tuple (near-unique within one match) instead of position.
                participants = parsed_state["participants"]
                by_kda = {
                    (p["kills"], p["deaths"], p["assists"]): p for p in participants
                }
                kda_order = detail_stats.get("kda", [])
                matched_count = 0
                for i, kda in enumerate(kda_order):
                    target = by_kda.get(tuple(kda))
                    if target is None:
                        continue
                    for stat_name in ("cs", "vision_score", "damage", "gold"):
                        values = detail_stats.get(stat_name, [])
                        if i < len(values):
                            target[stat_name] = values[i]
                    matched_count += 1
                st.session_state["ocr_parsed"] = parsed_state
                if matched_count < len(participants):
                    st.warning(
                        f"{matched_count}/{len(participants)}명만 KDA로 매칭됐습니다. "
                        "나머지는 표에서 직접 채워주세요."
                    )
                st.rerun()

        st.caption("파싱 결과 - raw_name이 참가자와 안 맞으면 직접 이름으로 고쳐주세요.")
        df = pd.DataFrame(parsed_state["participants"])
        edited = st.data_editor(df, num_rows="dynamic", key="ocr_edit_table", use_container_width=True)

        if parsed_state["winning_team_index"] is not None:
            detected_winner_label = f"{parsed_state['winning_team_index'] + 1}팀"
            st.info(f"자동 감지된 승리 팀: {detected_winner_label} (아래에서 확인/수정 가능)")
        else:
            st.warning("승리 팀을 자동으로 감지하지 못했습니다. 아래에서 직접 선택해주세요.")

        for _, row in edited.iterrows():
            player = all_players.get(row.get("raw_name"))
            if player is not None:
                ocr_stats_by_player_id[player.id] = {
                    "kills": int(row.get("kills") or 0),
                    "deaths": int(row.get("deaths") or 0),
                    "assists": int(row.get("assists") or 0),
                    "cs": int(row.get("cs") or 0),
                    "gold": int(row.get("gold") or 0),
                    "damage": int(row.get("damage") or 0),
                    "vision_score": int(row.get("vision_score") or 0),
                }

        if st.button("스크린샷 데이터 지우기"):
            del st.session_state["ocr_parsed"]
            st.rerun()

    labels = list(team_options.keys())
    default_index = labels.index(detected_winner_label) if detected_winner_label in labels else 0
    winner_label = st.selectbox("승리 팀", labels, index=default_index)
    note = st.text_area("비고", "")

    if st.button("경기 결과 저장"):
        match_service = MatchService(
            session,
            server_id,
            contribution_calculator=OCRContributionScoreCalculator() if ocr_stats_by_player_id else None,
        )
        try:
            match = match_service.record_match(
                teams=result.teams,
                winning_team_index=team_options[winner_label],
                actor_role=actor.role,
                note=note or None,
                match_stats_by_player_id=ocr_stats_by_player_id,
            )
        except PermissionDeniedError as exc:
            st.error(f"권한이 없습니다: {exc}")
        else:
            st.success(f"경기 저장 완료 (AI MVP: player_id={match.ai_mvp_player_id})")
            for key in ("last_balance_result", "ocr_parsed"):
                st.session_state.pop(key, None)
