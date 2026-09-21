from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.models.server_membership import ServerMembership
from app.models.vote import Vote
from app.services.vote_service import VoteService

router = APIRouter(prefix="/servers/{server_id}/matches/{match_id}/votes", tags=["votes"])


class CastVoteRequest(BaseModel):
    voter_player_id: int
    voted_player_id: int


@router.post("", response_model=Vote)
def cast_vote(
    server_id: int,
    match_id: int,
    payload: CastVoteRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Vote:
    return VoteService(db, server_id).cast_vote(
        match_id, payload.voter_player_id, payload.voted_player_id, actor.role
    )


@router.get("/tally", response_model=Optional[int])
def tally_user_mvp(server_id: int, match_id: int, db: Session = Depends(get_db)) -> Optional[int]:
    return VoteService(db, server_id).tally_user_mvp(match_id)
