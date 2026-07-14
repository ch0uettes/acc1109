from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Vote(BaseModel):
    id: Optional[int] = None
    server_id: Optional[int] = None
    match_id: int
    voter_player_id: int
    voted_player_id: int
