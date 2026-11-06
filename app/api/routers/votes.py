from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.models.server_membership import ServerMembership
from app.models.vote import Vote
from app.services.rbac import Permission, require_permission
from app.services.server_service import ServerService
from app.services.vote_service import VoteService
from app.utils.exceptions import InvalidVoteError

router = APIRouter(prefix="/servers/{server_id}/matches/{match_id}/votes", tags=["votes"], dependencies=[Depends(get_actor)])


class CastVoteRequest(BaseModel):
    voted_player_id: int
    # Admins only: record a vote on someone else's behalf (e.g. one sent on
    # Discord). Omitted = vote as yourself.
    voter_player_id: Optional[int] = None


@router.post("", response_model=Vote)
def cast_vote(
    server_id: int,
    match_id: int,
    payload: CastVoteRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Vote:
    own = ServerService(db).linked_player(actor)
    voter_id = payload.voter_player_id
    if voter_id is None or (own is not None and voter_id == own.id):
        if own is None:
            raise InvalidVoteError("로그인 이름과 연결된 참가자가 없어 투표할 수 없습니다. 관리자에게 연결을 요청해주세요")
        voter_id = own.id
    else:
        require_permission(actor.role, Permission.VOTE_ON_BEHALF)
    return VoteService(db, server_id).cast_vote(match_id, voter_id, payload.voted_player_id, actor.role)


@router.get("/tally", response_model=Optional[int])
def tally_user_mvp(server_id: int, match_id: int, db: Session = Depends(get_db)) -> Optional[int]:
    return VoteService(db, server_id).tally_user_mvp(match_id)


class VoteCount(BaseModel):
    player_id: int
    votes: int


class VoteSummary(BaseModel):
    participant_count: int
    counts: list[VoteCount]
    voter_player_ids: list[int]
    leader_player_ids: list[int]


@router.get("/summary", response_model=VoteSummary)
def vote_summary(server_id: int, match_id: int, db: Session = Depends(get_db)) -> VoteSummary:
    return VoteSummary(**VoteService(db, server_id).summary(match_id))
