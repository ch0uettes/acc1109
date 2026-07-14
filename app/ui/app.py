from __future__ import annotations

import streamlit as st

from app.config import settings, update_riot_api_key
from app.database.base import SessionLocal, init_db
from app.models.server_membership import ServerMembership
from app.services.server_service import ServerService
from app.ui.pages import match_page, player_page, server_admin_page, stats_page, team_page, vote_page

PAGES = {
    "참가자 관리": player_page.render,
    "팀 생성": team_page.render,
    "경기 저장": match_page.render,
    "MVP 투표": vote_page.render,
    "통계": stats_page.render,
    "서버 관리": server_admin_page.render,
}

ROLE_LABEL = {
    "OWNER": "Owner",
    "SERVER_ADMIN": "Server Admin",
    "MODERATOR": "Moderator",
    "PLAYER": "Player",
    "PLATFORM_ADMIN": "Platform Admin",
}


def run() -> None:
    st.set_page_config(page_title="AI Inhouse Balancer", layout="wide")
    init_db()

    st.sidebar.title("AI Inhouse Balancer")
    _render_riot_api_key()

    with SessionLocal() as session:
        server_service = ServerService(session)
        server_id = _render_server_picker(server_service)
        if server_id is None:
            st.info("먼저 사이드바에서 서버를 만들어주세요.")
            return

        actor = _render_actor_picker(server_service, server_id)

        st.sidebar.divider()
        choice = st.sidebar.radio("메뉴", list(PAGES.keys()))
        PAGES[choice](session, server_id, actor)


def _render_riot_api_key() -> None:
    """Riot developer keys expire every 24h, so this is a process-memory-only
    override (see app.config.update_riot_api_key) - not saved to disk/DB.
    Paste a fresh key here instead of restarting the app whenever the old
    one expires."""
    status = "설정됨" if settings.riot_api_key else "설정되지 않음"
    with st.sidebar.expander(f"Riot API 키 (임시 갱신) - {status}", expanded=not settings.riot_api_key):
        st.caption("Riot 개발자 키는 24시간마다 만료됩니다. 새 키를 붙여넣으면 앱을 재시작하지 않고 바로 적용됩니다 (재시작 시에는 초기화).")
        new_key = st.text_input("새 Riot API 키", type="password", key="riot_api_key_input")
        if st.button("적용", key="apply_riot_api_key_btn") and new_key:
            update_riot_api_key(new_key)
            st.success("Riot API 키를 갱신했습니다.")
            st.rerun()


def _render_server_picker(server_service: ServerService) -> int | None:
    servers = server_service.list_servers()

    with st.sidebar.expander("서버 추가", expanded=not servers):
        new_server_name = st.text_input("새 서버 이름", key="new_server_name")
        new_owner_name = st.text_input("내 이름 (Owner가 됩니다)", key="new_server_owner_name")
        if st.button("서버 만들기", key="create_server_btn") and new_server_name and new_owner_name:
            created = server_service.create_server(new_server_name, owner_display_name=new_owner_name)
            st.session_state["active_server_id"] = created.id
            st.rerun()

    servers = server_service.list_servers()
    if not servers:
        return None

    options = {s.name: s.id for s in servers}
    active_id = st.session_state.get("active_server_id", servers[0].id)
    labels = list(options.keys())
    ids = list(options.values())
    default_index = ids.index(active_id) if active_id in ids else 0

    chosen_label = st.sidebar.selectbox("서버", labels, index=default_index, key="server_picker")
    chosen_id = options[chosen_label]
    st.session_state["active_server_id"] = chosen_id
    return chosen_id


def _render_actor_picker(server_service: ServerService, server_id: int) -> ServerMembership:
    """Who is currently operating the app, and with what Role - every
    privileged service call is gated against this. There's no login system,
    so this is a self-attested picker (same limitation as before), but
    unlike the old admin-only picker every member (any Role) shows up here,
    and joining as a base Player requires no permission at all."""
    members = server_service.list_members(server_id)

    with st.sidebar.expander("멤버 등록 (Player로 참가)", expanded=not members):
        new_member_name = st.text_input("내 이름", key="new_member_name")
        if st.button("참가", key="add_member_btn") and new_member_name:
            server_service.add_player_member(server_id, new_member_name)
            st.rerun()

    members = server_service.list_members(server_id)
    labels = [f"{m.display_name} ({ROLE_LABEL[m.role.value]})" for m in members]
    chosen_label = st.sidebar.selectbox("내 계정", labels, key="actor_picker")
    return members[labels.index(chosen_label)]
