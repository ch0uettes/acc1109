from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from sqlalchemy.orm import Session

from app.models.player import Player
from app.models.server_membership import ServerMembership
from app.ocr.extractor import build_ocr_extractor
from app.rating.official import master_stage_from
from app.rating.resolver import TierSnapshot
from app.services.player_service import PlayerService
from app.services.rbac import Permission, has_permission
from app.utils.exceptions import AppError, PermissionDeniedError
from app.utils.enums import Division, Position, RatingSource, Tier

# UNRANKED only ever comes from having no current-season rank at all - it's
# not a tier anyone should pick by hand, so it's excluded from every tier
# dropdown except the edit form (which has to be able to display it).
RANKED_TIERS = [t for t in Tier if t != Tier.UNRANKED]

RATING_SOURCE_LABEL = {
    RatingSource.CURRENT_SEASON: "현재 시즌",
    RatingSource.MANUAL: "직접 입력",
    RatingSource.SEED: "Seed(운영자 판단)",
}

NO_SUB_ROLE = "없음"


def _sub_role_selectbox(label: str, key: str, default: Position | None = None) -> Position | None:
    """부 포지션은 선택 사항이라 '없음'을 진짜 옵션으로 취급해야 st.selectbox의
    빈 상태를 흉내 내지 않고도 자연스럽게 다룰 수 있다."""
    options: list[str | Position] = [NO_SUB_ROLE, *list(Position)]
    index = options.index(default) if default is not None else 0
    choice = st.selectbox(
        label, options, index=index, key=key, format_func=lambda x: x if x == NO_SUB_ROLE else x.value
    )
    return None if choice == NO_SUB_ROLE else choice


def _tier_display(tier: Tier | None, division: Division | None, lp: int | None) -> str:
    if tier is None:
        return "-"
    if tier == Tier.MASTER:
        return f"마스터 {master_stage_from(tier, lp or 0)}"
    if tier == Tier.UNRANKED:
        return "-"
    return f"{tier.value} {division.value if division else ''} {lp if lp is not None else ''}".strip()


def render(session: Session, server_id: int, actor: ServerMembership) -> None:
    st.header("참가자 관리")
    service = PlayerService(session, server_id)

    tab_manual, tab_riot, tab_bulk = st.tabs(["수동 입력", "Riot ID로 자동 조회", "스크린샷으로 일괄 등록"])

    with tab_manual:
        _render_manual_tab(service, actor)

    with tab_riot:
        _render_riot_tab(service, actor)

    with tab_bulk:
        _render_bulk_ocr_tab(service, actor)

    st.subheader("참가자 목록")
    players = service.list_players()
    if not players:
        st.info("등록된 참가자가 없습니다.")
        return

    st.dataframe(
        [
            {
                "닉네임": p.nickname,
                "현재 티어": _tier_display(p.tier, p.division, p.lp),
                "최고 티어": _tier_display(p.peak_tier, p.peak_division, p.peak_lp),
                "최고 티어 달성 시즌": p.peak_achieved_season or ("직접 입력" if p.peak_tier else "-"),
                "주 포지션": p.main_role.value,
                "부 포지션": p.sub_role.value if p.sub_role else None,
                "Riot 추천": (
                    f"{p.recommended_main_role.value}"
                    + (f"/{p.recommended_sub_role.value}" if p.recommended_sub_role else "")
                    if p.recommended_main_role
                    else None
                ),
                "Official": round(p.official_rating, 1) if p.official_rating is not None else None,
                "Seed": round(p.seed_rating, 1) if p.seed_rating is not None else None,
                "Internal": round(p.internal_rating, 1),
                "Final": round(p.final_rating, 1),
                "출처": RATING_SOURCE_LABEL[p.rating_source],
                "신뢰도": f"{p.confidence:.0%}",
                "캘리브레이션": "진행중" if p.calibration_mode else "",
                "게임 수": p.games_played,
            }
            for p in players
        ],
        use_container_width=True,
    )

    _render_edit_delete(service, players, actor)


def _render_manual_tab(service: PlayerService, actor: ServerMembership) -> None:
    st.caption("운영자가 실제 티어를 정확히 아는 경우에만 사용하세요 (예: Riot ID 연동 없이 추가).")
    with st.form("add_player_manual"):
        col1, col2, col3 = st.columns(3)
        nickname = col1.text_input("닉네임")
        tier = col2.selectbox("현재 티어", RANKED_TIERS)
        division = col3.selectbox("현재 디비전 (마스터는 무시됨)", list(Division))
        lp = st.number_input("현재 LP", min_value=0, max_value=3000, value=0)
        rcol1, rcol2 = st.columns(2)
        main_role = rcol1.selectbox("주 포지션", list(Position), key="manual_main_role")
        sub_role = _sub_role_selectbox("부 포지션 (선택)", key="manual_sub_role")

        st.caption("최고 티어 (선택) - 현재 티어와 200점 이상 차이 나면 base rating 계산에 가중 반영됩니다.")
        no_peak = st.checkbox("최고 티어 정보 없음", key="manual_no_peak")
        pcol1, pcol2, pcol3 = st.columns(3)
        peak_tier = pcol1.selectbox("최고 티어", RANKED_TIERS, disabled=no_peak, key="manual_peak_tier")
        peak_division = pcol2.selectbox(
            "최고 디비전", list(Division), disabled=no_peak, key="manual_peak_division"
        )
        peak_lp = pcol3.number_input(
            "최고 LP", min_value=0, max_value=3000, value=0, disabled=no_peak, key="manual_peak_lp"
        )

        submitted = st.form_submit_button("참가자 추가")

        if submitted and nickname:
            try:
                service.create_player(
                    Player(
                        nickname=nickname,
                        tier=tier,
                        division=division,
                        lp=int(lp),
                        peak_tier=None if no_peak else peak_tier,
                        peak_division=None if no_peak else peak_division,
                        peak_lp=None if no_peak else int(peak_lp),
                        rating_source=RatingSource.MANUAL,
                        main_role=main_role,
                        sub_role=sub_role,
                    ),
                    actor_role=actor.role,
                )
            except PermissionDeniedError as exc:
                st.error(f"권한이 없습니다: {exc}")
            else:
                st.success(f"{nickname} 추가 완료")
                st.rerun()


def _render_riot_tab(service: PlayerService, actor: ServerMembership) -> None:
    st.caption("Riot ID의 '#' 앞부분(게임 이름)과 뒷부분(태그)을 나눠서 입력하세요. 예: Hide on bush#KR1")

    nickname = st.text_input("내전에서 쓸 닉네임", key="riot_nickname")
    col1, col2 = st.columns(2)
    game_name = col1.text_input("게임 이름", key="riot_game_name")
    tag_line = col2.text_input("태그", key="riot_tag_line")

    if st.button("Riot ID 조회 (포지션 자동 분석 포함)"):
        if not (nickname and game_name and tag_line):
            st.warning("닉네임, 게임 이름, 태그를 모두 입력해주세요.")
        else:
            try:
                with st.spinner("현재 시즌 랭크 조회 + 최근 랭크 게임으로 주/부 포지션 분석 중..."):
                    puuid, current = service.probe_current_season(game_name, tag_line)
                    recommendation = service.infer_position(puuid)
            except NotImplementedError as exc:
                st.error(f"{exc} — 환경변수 RIOT_API_KEY를 설정해주세요.")
            except requests.HTTPError as exc:
                st.error(f"Riot API 조회 실패: {exc}")
            else:
                opgg_peak = service.fetch_peak_from_opgg(game_name, tag_line)
                # New probe -> reset any stale peak-field widget state so the
                # freshly fetched (or absent) OP.GG value actually takes
                # effect as the selectbox default below.
                for widget_key in ("riot_no_peak", "riot_peak_tier", "riot_peak_division", "riot_peak_lp"):
                    st.session_state.pop(widget_key, None)
                st.session_state["riot_probe"] = {
                    "puuid": puuid,
                    "current": current,
                    "nickname": nickname,
                    "recommendation": recommendation,
                    "opgg_peak": opgg_peak,
                }

    probe = st.session_state.get("riot_probe")
    if probe is None:
        return

    current: TierSnapshot | None = probe["current"]

    recommendation = probe["recommendation"]
    if recommendation is not None:
        sub_text = (
            f" / 부: **{recommendation.sub.value}** (비율 {recommendation.sub_ratio:.0%})"
            if recommendation.sub is not None
            else ""
        )
        st.info(
            f"Riot 추천 (참고용, 최종 결정은 아래에서 직접) - 주: **{recommendation.main.value}** "
            f"(비율 {recommendation.main_ratio:.0%}, 표본 {recommendation.sample_size}판){sub_text}"
        )
    else:
        st.warning("랭크 게임 이력이 없어 포지션을 자동 분석할 수 없습니다. 직접 선택해주세요.")

    rcol1, rcol2 = st.columns(2)
    main_index = list(Position).index(recommendation.main) if recommendation else 0
    main_role = rcol1.selectbox(
        "주 포지션 (Riot 추천으로 미리 채워짐, 직접 수정 가능)", list(Position), index=main_index, key="riot_main_role"
    )
    sub_role = _sub_role_selectbox(
        "부 포지션 (선택)",
        key="riot_sub_role",
        default=recommendation.sub if recommendation else None,
    )

    st.caption("최고 티어 (선택) - 참고용이 아니라, 현재 티어와 200점 이상 차이 나면 base rating 계산에 가중 반영됩니다.")
    opgg_peak: tuple[TierSnapshot, str] | None = probe.get("opgg_peak")
    if opgg_peak is not None:
        fetched_snapshot, fetched_season = opgg_peak
        st.caption(
            f"출처: OP.GG - 자동으로 찾은 최고 티어({fetched_season} 시즌)로 아래 값이 채워졌습니다. "
            "필요하면 직접 수정하세요."
        )
    else:
        st.caption("OP.GG에서 최고 티어 이력을 찾지 못했습니다 - 알고 있다면 직접 입력해주세요 (선택 사항).")

    no_peak = st.checkbox("최고 티어 정보 없음", value=opgg_peak is None, key="riot_no_peak")
    pcol1, pcol2, pcol3 = st.columns(3)
    peak_tier = pcol1.selectbox(
        "최고 티어",
        RANKED_TIERS,
        index=RANKED_TIERS.index(fetched_snapshot.tier) if opgg_peak is not None else 0,
        disabled=no_peak,
        key="riot_peak_tier",
    )
    peak_division = pcol2.selectbox(
        "최고 디비전",
        list(Division),
        index=list(Division).index(fetched_snapshot.division) if opgg_peak is not None else 0,
        disabled=no_peak,
        key="riot_peak_division",
    )
    peak_lp = pcol3.number_input(
        "최고 LP",
        min_value=0,
        max_value=3000,
        value=fetched_snapshot.lp if opgg_peak is not None else 0,
        disabled=no_peak,
        key="riot_peak_lp",
    )
    peak = None if no_peak else TierSnapshot(peak_tier, peak_division, int(peak_lp))

    peak_achieved_season = None
    if (
        opgg_peak is not None
        and peak is not None
        and peak.tier == fetched_snapshot.tier
        and peak.division == fetched_snapshot.division
        and peak.lp == fetched_snapshot.lp
    ):
        peak_achieved_season = fetched_season

    seed_tier = None
    seed_division = Division.III
    seed_reason = None
    if current is not None:
        st.success(f"현재 시즌 랭크: {current.tier.value} {current.division.value} {current.lp}LP")
    else:
        st.warning(
            "현재 시즌 언랭입니다. 이 플레이어는 실력을 스스로 신고할 수 없습니다 - "
            "운영자가 직접 판단한 초기 Seed Rating 티어를 선택해주세요."
        )
        scol1, scol2 = st.columns(2)
        seed_tier = scol1.selectbox("Seed Rating 티어 (운영자 판단)", RANKED_TIERS, key="riot_seed_tier")
        seed_division = scol2.selectbox(
            "Seed Rating 디비전", list(Division), index=list(Division).index(Division.III), key="riot_seed_division"
        )
        seed_reason = st.text_input("판단 사유 (선택)", key="riot_seed_reason")

    if st.button("참가자 추가", key="riot_confirm_add"):
        try:
            player = service.register_player(
                probe["nickname"],
                probe["puuid"],
                main_role,
                current,
                peak,
                actor_role=actor.role,
                seed_tier=seed_tier,
                seed_division=seed_division,
                changed_by=actor.display_name,
                reason=seed_reason or None,
                sub_role=sub_role,
                recommendation=recommendation,
                peak_achieved_season=peak_achieved_season,
            )
        except PermissionDeniedError as exc:
            st.error(f"권한이 없습니다: {exc}")
        else:
            peak_note = f", 최고 티어 출처: OP.GG ({peak_achieved_season})" if peak_achieved_season else ""
            st.success(
                f"{player.nickname} 추가 완료 (출처: {RATING_SOURCE_LABEL[player.rating_source]}, "
                f"신뢰도 {player.confidence:.0%}{peak_note})"
            )
            del st.session_state["riot_probe"]
            st.rerun()


def _render_bulk_ocr_tab(service: PlayerService, actor: ServerMembership) -> None:
    """Bulk version of _render_riot_tab: one screenshot containing a whole
    roster's nickname + Riot ID (game#tag) per row, instead of typing each
    player in one at a time. Same "OCR gives a first draft, human reviews
    before anything is saved" contract as match_page.py's screenshot flow -
    the extracted table is always editable before the actual Riot lookups/
    registrations run.

    Only auto-registers players who have a current-season rank (Official
    Rating - no operator judgment required). An unranked player needs an
    operator's own Seed Rating judgment (see PlayerService.register_player's
    seed_tier requirement) - guessing that automatically for a whole batch
    would violate this app's core rule that skill is never self-reported
    and never silently assumed, so those rows are reported back for manual
    handling via the other two tabs instead of being registered here."""
    st.caption(
        "닉네임과 라이엇 아이디(태그 포함)가 함께 보이는 참가자 명단 스크린샷을 업로드하면 "
        "OCR로 읽어 표로 보여줍니다. 표에서 확인/수정 후 일괄 등록하세요."
    )
    uploaded = st.file_uploader(
        "참가자 명단 스크린샷 업로드", type=["png", "jpg", "jpeg"], key="bulk_riot_uploader"
    )

    if uploaded is not None and st.button("스크린샷 분석", key="bulk_riot_analyze"):
        with tempfile.NamedTemporaryFile(suffix=Path(uploaded.name).suffix, delete=False) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name

        try:
            with st.spinner("닉네임/라이엇 아이디 인식 중..."):
                extractor = build_ocr_extractor()
                rows = extractor.extract_riot_ids(tmp_path)
        except NotImplementedError as exc:
            st.error(str(exc))
        else:
            if not rows:
                st.warning("스크린샷에서 '이름#태그' 형태의 라이엇 아이디를 찾지 못했습니다.")
            st.session_state["bulk_riot_ocr"] = [row.model_dump() for row in rows]

    parsed_rows = st.session_state.get("bulk_riot_ocr")
    if not parsed_rows:
        return

    st.caption("파싱 결과 - 닉네임/게임 이름/태그가 잘못 읽혔다면 직접 고쳐주세요. 필요 없는 행은 삭제해도 됩니다.")
    edited = st.data_editor(
        pd.DataFrame(parsed_rows)[["nickname", "game_name", "tag_line"]],
        num_rows="dynamic",
        key="bulk_riot_edit_table",
        use_container_width=True,
    )

    if st.button("일괄 조회 및 추가", key="bulk_riot_confirm_add"):
        added: list[str] = []
        needs_manual: list[str] = []
        failed: list[tuple[str, str]] = []

        for _, row in edited.iterrows():
            nickname = str(row.get("nickname") or "").strip()
            game_name = str(row.get("game_name") or "").strip()
            tag_line = str(row.get("tag_line") or "").strip()
            if not (nickname and game_name and tag_line):
                failed.append((nickname or game_name or "(빈 행)", "닉네임/게임 이름/태그 중 비어 있는 값이 있습니다"))
                continue

            try:
                puuid, current = service.probe_current_season(game_name, tag_line)
            except NotImplementedError as exc:
                failed.append((nickname, str(exc)))
                continue
            except requests.HTTPError as exc:
                failed.append((nickname, f"Riot API 조회 실패: {exc}"))
                continue

            if current is None:
                needs_manual.append(nickname)
                continue

            recommendation = service.infer_position(puuid)
            main_role = recommendation.main if recommendation else Position.MID
            sub_role = recommendation.sub if recommendation else None
            opgg_result = service.fetch_peak_from_opgg(game_name, tag_line)
            peak = opgg_result[0] if opgg_result else None
            peak_achieved_season = opgg_result[1] if opgg_result else None

            try:
                player = service.register_player(
                    nickname,
                    puuid,
                    main_role,
                    current,
                    peak=peak,
                    actor_role=actor.role,
                    changed_by=actor.display_name,
                    sub_role=sub_role,
                    recommendation=recommendation,
                    peak_achieved_season=peak_achieved_season,
                )
            except PermissionDeniedError as exc:
                failed.append((nickname, f"권한이 없습니다: {exc}"))
                continue
            except AppError as exc:
                failed.append((nickname, str(exc)))
                continue
            except Exception as exc:  # noqa: BLE001 - a duplicate nickname/puuid/discord_id
                # raises a raw IntegrityError (unique constraint), not an
                # AppError - one bad row must not abort the whole batch.
                failed.append((nickname, f"등록 실패 (이미 존재하는 참가자일 수 있음): {exc}"))
                continue

            peak_note = f", 최고 티어 출처: OP.GG ({peak_achieved_season})" if peak_achieved_season else ""
            added.append(f"{player.nickname} ({RATING_SOURCE_LABEL[player.rating_source]}{peak_note})")

        del st.session_state["bulk_riot_ocr"]

        if added:
            st.success(f"{len(added)}명 추가 완료: " + ", ".join(added))
        if needs_manual:
            st.warning(
                f"{len(needs_manual)}명은 현재 시즌 언랭이라 운영자 판단(Seed Rating)이 필요합니다 - "
                "'Riot ID로 자동 조회' 탭에서 개별 등록해주세요: " + ", ".join(needs_manual)
            )
        if failed:
            st.error("등록 실패:\n" + "\n".join(f"- {name}: {reason}" for name, reason in failed))


def _render_edit_delete(service: PlayerService, players: list[Player], actor: ServerMembership) -> None:
    st.subheader("참가자 수정 / 삭제")
    target_options = {f"{p.nickname} ({p.tier.value})": p for p in players}
    target_label = st.selectbox("대상 선택", list(target_options.keys()), key="edit_target")
    target = target_options[target_label]

    edit_tiers = list(Tier) if target.tier == Tier.UNRANKED else RANKED_TIERS

    with st.form("edit_player"):
        col1, col2, col3 = st.columns(3)
        new_tier = col1.selectbox("현재 티어", edit_tiers, index=edit_tiers.index(target.tier))
        new_division = col2.selectbox(
            "현재 디비전", list(Division), index=list(Division).index(target.division)
        )
        new_lp = col3.number_input("현재 LP", min_value=0, max_value=3000, value=target.lp)
        rcol1, rcol2 = st.columns(2)
        new_main_role = rcol1.selectbox(
            "주 포지션", list(Position), index=list(Position).index(target.main_role), key="edit_main_role"
        )
        new_sub_role = _sub_role_selectbox("부 포지션 (선택)", key="edit_sub_role", default=target.sub_role)

        st.caption("최고 티어 - 현재 티어와 200점 이상 차이 나면 base rating 계산에 가중 반영됩니다.")
        if target.peak_achieved_season:
            st.caption(f"현재 저장된 값의 출처: OP.GG ({target.peak_achieved_season}) - 아래 값을 직접 바꾸면 이 출처 표시는 사라집니다.")
        no_peak = st.checkbox("최고 티어 정보 없음", value=target.peak_tier is None, key="edit_no_peak")
        pcol1, pcol2, pcol3 = st.columns(3)
        new_peak_tier = pcol1.selectbox(
            "최고 티어",
            RANKED_TIERS,
            index=RANKED_TIERS.index(target.peak_tier) if target.peak_tier else 0,
            disabled=no_peak,
            key="edit_peak_tier",
        )
        new_peak_division = pcol2.selectbox(
            "최고 디비전",
            list(Division),
            index=list(Division).index(target.peak_division) if target.peak_division else 0,
            disabled=no_peak,
            key="edit_peak_division",
        )
        new_peak_lp = pcol3.number_input(
            "최고 LP",
            min_value=0,
            max_value=3000,
            value=target.peak_lp or 0,
            disabled=no_peak,
            key="edit_peak_lp",
        )

        can_override_rating = has_permission(actor.role, Permission.SET_SEED_RATING)
        st.caption(
            "Internal Rating Override (관리자 전용) - 내전 전용 실력 지표를 직접 보정합니다. "
            "평소에는 경기 결과로 자동 갱신되므로, 명백히 잘못됐다고 판단될 때만 사용하세요."
        )
        new_internal_rating = st.number_input(
            "Internal Rating 직접 수정",
            value=float(target.internal_rating),
            disabled=not can_override_rating,
            key="edit_internal_rating_override",
        )
        internal_rating_reason = st.text_input(
            "Internal Rating 변경 사유 (선택)", disabled=not can_override_rating, key="edit_internal_rating_reason"
        )

        is_seed = new_tier == Tier.UNRANKED
        new_seed_tier = None
        new_seed_division = Division.III
        seed_reason = None
        if is_seed:
            st.caption("현재 티어가 UNRANKED이므로 Seed Rating 티어(운영자 판단)를 지정해주세요. 변경 이력이 기록됩니다.")
            default_seed_index = (
                RANKED_TIERS.index(target.peak_tier)
                if target.rating_source == RatingSource.SEED and target.peak_tier in RANKED_TIERS
                else 0
            )
            secol1, secol2 = st.columns(2)
            new_seed_tier = secol1.selectbox(
                "Seed Rating 티어", RANKED_TIERS, index=default_seed_index, key="edit_seed_tier"
            )
            new_seed_division = secol2.selectbox(
                "Seed Rating 디비전",
                list(Division),
                index=list(Division).index(Division.III),
                key="edit_seed_division",
            )
            seed_reason = st.text_input("변경 사유", key="edit_seed_reason")

        col_update, col_delete = st.columns(2)
        do_update = col_update.form_submit_button("수정 저장")
        do_delete = col_delete.form_submit_button("삭제")

        if do_update:
            new_peak_snapshot = (
                None if no_peak else (new_peak_tier, new_peak_division, int(new_peak_lp))
            )
            old_peak_snapshot = (
                None
                if target.peak_tier is None
                else (target.peak_tier, target.peak_division, target.peak_lp)
            )
            # A manual edit that changes the peak values invalidates any
            # OP.GG-sourced season label - unchanged values keep it.
            peak_achieved_season = (
                target.peak_achieved_season if new_peak_snapshot == old_peak_snapshot else None
            )
            try:
                if is_seed:
                    # Seed Rating changes always go through set_seed_rating() so
                    # they're audited (old/new value, who, when, why). It does
                    # its own persist, so the follow-up field edits must build
                    # on ITS result, not the stale `target` snapshot - otherwise
                    # this second update would clobber the seed_rating it just set.
                    after_seed = service.set_seed_rating(
                        target.id,
                        new_seed_tier,
                        changed_by=actor.display_name,
                        actor_role=actor.role,
                        seed_division=new_seed_division,
                        reason=seed_reason or None,
                    )
                    updated = after_seed.model_copy(
                        update={
                            "division": new_division,
                            "lp": int(new_lp),
                            "peak_tier": None if no_peak else new_peak_tier,
                            "peak_division": None if no_peak else new_peak_division,
                            "peak_lp": None if no_peak else int(new_peak_lp),
                            "peak_achieved_season": peak_achieved_season,
                            "main_role": new_main_role,
                            "sub_role": new_sub_role,
                        }
                    )
                    service.update_player(updated, actor_role=actor.role)
                else:
                    updated = target.model_copy(
                        update={
                            "tier": new_tier,
                            "division": new_division,
                            "lp": int(new_lp),
                            "peak_tier": None if no_peak else new_peak_tier,
                            "peak_division": None if no_peak else new_peak_division,
                            "peak_lp": None if no_peak else int(new_peak_lp),
                            "peak_achieved_season": peak_achieved_season,
                            "main_role": new_main_role,
                            "sub_role": new_sub_role,
                            "rating_source": RatingSource.MANUAL,
                            "seed_rating": None,
                        }
                    )
                    service.update_player(updated, actor_role=actor.role)

                if can_override_rating and new_internal_rating != target.internal_rating:
                    service.override_internal_rating(
                        target.id,
                        float(new_internal_rating),
                        actor.role,
                        changed_by=actor.display_name,
                        reason=internal_rating_reason or None,
                    )
            except PermissionDeniedError as exc:
                st.error(f"권한이 없습니다: {exc}")
            except AppError as exc:
                st.error(str(exc))
            else:
                st.success(f"{target.nickname} 수정 완료")
                st.rerun()

        if do_delete:
            try:
                service.deactivate_player(target.id, actor_role=actor.role)
            except PermissionDeniedError as exc:
                st.error(f"권한이 없습니다: {exc}")
            except AppError as exc:
                st.error(str(exc))
            else:
                st.success(f"{target.nickname} 삭제 완료 (경기/레이팅 이력은 보존됩니다)")
                st.rerun()
