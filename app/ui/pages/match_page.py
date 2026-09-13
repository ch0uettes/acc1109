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


def _match_detail_stats_by_kda(
    participants: list[dict], detail_stats: dict[str, list]
) -> tuple[int, list[str]]:
    """Joins the detail (CS/vision/damage/gold) screenshot's columns back to
    the main scoreboard's participants by K/D/A - the detail screenshot has
    no names, and its column order isn't guaranteed to match the
    scoreboard's row order (observed directly: one team's order matched,
    the other team's didn't), so KDA is the most reliable join key
    available. It is not a true identifier though: two participants can
    genuinely share one (e.g. two 0/0/0 supports in a short game). Mutates
    each *unambiguously* matched participant dict in place with its stats.
    Returns (matched_count, ambiguous_names) - names sharing a KDA with at
    least one other participant are deliberately left unmatched rather than
    guessed, since silently assigning one player's stats to a different
    player who happens to share their KDA would be wrong data with no
    indication anything went wrong."""
    by_kda: dict[tuple[int, int, int], list[dict]] = {}
    for p in participants:
        by_kda.setdefault((p["kills"], p["deaths"], p["assists"]), []).append(p)
    ambiguous_names = [p["raw_name"] for group in by_kda.values() if len(group) > 1 for p in group]

    kda_order = detail_stats.get("kda", [])
    matched_count = 0
    for i, kda in enumerate(kda_order):
        candidates = by_kda.get(tuple(kda), [])
        if len(candidates) != 1:
            continue
        target = candidates[0]
        for stat_name in ("cs", "vision_score", "damage", "gold"):
            values = detail_stats.get(stat_name, [])
            if i < len(values):
                target[stat_name] = values[i]
        matched_count += 1
    return matched_count, ambiguous_names


def _is_stale_ocr(ocr_parsed_token: str | None, current_match_token: str | None) -> bool:
    """True when previously-parsed OCR data was captured under a different
    match context (a different saved team combo) than the one now active -
    see team_page.py's save handler for why reusing it across combos is
    unsafe. A missing token on either side (nothing parsed yet, or a combo
    saved before this token existed) is conservatively treated as stale."""
    return ocr_parsed_token != current_match_token


def render(session: Session, server_id: int, actor: ServerMembership) -> None:
    st.header("경기 저장")
    result = st.session_state.get("last_balance_result")
    if result is None:
        st.info("먼저 '팀 생성' 메뉴에서 팀을 만들어주세요.")
        return

    # ocr_parsed is stamped (below) with whatever match_context_token was
    # current when it was parsed. team_page.py mints a new token every time
    # a *different* combo is saved into last_balance_result, so a token
    # mismatch here means this OCR data was read for an earlier combo, not
    # the one we're about to record a match for - it must not carry over
    # (see team_page.py's save handler for why: overlapping rosters would
    # otherwise silently inherit the wrong K/D/A). No token at all (a combo
    # saved before this token scheme existed in this session) is treated
    # the same way, for safety.
    current_token = st.session_state.get("match_context_token")
    if _is_stale_ocr(st.session_state.get("ocr_parsed_token"), current_token):
        st.session_state.pop("ocr_parsed", None)
        st.session_state.pop("ocr_parsed_token", None)

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
            st.session_state["ocr_parsed_token"] = current_token

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
                participants = parsed_state["participants"]
                matched_count, ambiguous_names = _match_detail_stats_by_kda(participants, detail_stats)
                st.session_state["ocr_parsed"] = parsed_state
                if matched_count < len(participants):
                    message = f"{matched_count}/{len(participants)}명만 KDA로 매칭됐습니다. 나머지는 표에서 직접 채워주세요."
                    if ambiguous_names:
                        message += f" (KDA가 겹쳐 자동 매칭이 불가능한 참가자: {', '.join(ambiguous_names)})"
                    st.warning(message)
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
            st.session_state.pop("ocr_parsed", None)
            st.session_state.pop("ocr_parsed_token", None)
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
            for key in ("last_balance_result", "ocr_parsed", "ocr_parsed_token", "match_context_token"):
                st.session_state.pop(key, None)
