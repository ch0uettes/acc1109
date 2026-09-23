from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.models.internal_rating_change import InternalRatingChange
from app.models.player import Player
from app.models.season_rank import PlayerSeasonRank
from app.models.seed_rating_change import SeedRatingChange
from app.models.server_membership import ServerMembership
from app.ocr.schemas import OCRRiotIdRow
from app.position.schemas import RoleRecommendation
from app.rating.resolver import TierSnapshot
from app.roster_import import UnsupportedRosterFileError, parse_roster_file
from app.services.player_service import PlayerService
from app.utils.enums import Division, Position, Tier

router = APIRouter(prefix="/servers/{server_id}/players", tags=["players"])


class CreatePlayerRequest(BaseModel):
    """Manual-entry path - the operator has typed an exact tier they know
    to be true (see PlayerService.create_player)."""

    nickname: str
    tier: Tier
    division: Division = Division.IV
    lp: int = 0
    peak_tier: Optional[Tier] = None
    peak_division: Optional[Division] = None
    peak_lp: Optional[int] = None
    main_role: Position
    sub_role: Optional[Position] = None


class ProbeRequest(BaseModel):
    game_name: str
    tag_line: str


class ProbeResponse(BaseModel):
    puuid: str
    current: Optional[TierSnapshot]


class RegisterPlayerRequest(BaseModel):
    nickname: str
    puuid: str
    main_role: Position
    sub_role: Optional[Position] = None
    current: Optional[TierSnapshot] = None
    peak: Optional[TierSnapshot] = None
    seed_tier: Optional[Tier] = None
    seed_division: Division = Division.III
    peak_achieved_season: Optional[str] = None
    recommendation: Optional[RoleRecommendation] = None
    reason: Optional[str] = None


class SeedRatingRequest(BaseModel):
    seed_tier: Tier
    seed_division: Division = Division.III
    reason: Optional[str] = None


class InternalRatingOverrideRequest(BaseModel):
    new_internal_rating: float
    reason: Optional[str] = None


def _service(server_id: int, db: Session) -> PlayerService:
    return PlayerService(db, server_id)


@router.get("", response_model=list[Player])
def list_players(server_id: int, include_inactive: bool = False, db: Session = Depends(get_db)) -> list[Player]:
    return _service(server_id, db).list_players(include_inactive=include_inactive)


@router.get("/{player_id}", response_model=Player)
def get_player(server_id: int, player_id: int, db: Session = Depends(get_db)) -> Player:
    return _service(server_id, db).get_player(player_id)


@router.post("", response_model=Player)
def create_player(
    server_id: int,
    payload: CreatePlayerRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Player:
    player = Player(
        nickname=payload.nickname,
        tier=payload.tier,
        division=payload.division,
        lp=payload.lp,
        peak_tier=payload.peak_tier,
        peak_division=payload.peak_division,
        peak_lp=payload.peak_lp,
        main_role=payload.main_role,
        sub_role=payload.sub_role,
    )
    return _service(server_id, db).create_player(player, actor.role)


@router.post("/roster-file", response_model=list[OCRRiotIdRow])
async def parse_roster_upload(server_id: int, file: UploadFile = File(...)) -> list[OCRRiotIdRow]:
    """CSV/TXT/XLSX counterpart to the screenshot-OCR bulk-registration
    path (see /ocr/riot-ids) - both feed the same nickname/game_name/
    tag_line review table, a file is just a more reliable input than OCR
    when the operator already has one."""
    try:
        return parse_roster_file(await file.read(), file.filename or "roster")
    except UnsupportedRosterFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/probe", response_model=ProbeResponse)
def probe_current_season(server_id: int, payload: ProbeRequest, db: Session = Depends(get_db)) -> ProbeResponse:
    puuid, current = _service(server_id, db).probe_current_season(payload.game_name, payload.tag_line)
    return ProbeResponse(puuid=puuid, current=current)


@router.post("/register", response_model=Player)
def register_player(
    server_id: int,
    payload: RegisterPlayerRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Player:
    return _service(server_id, db).register_player(
        nickname=payload.nickname,
        puuid=payload.puuid,
        main_role=payload.main_role,
        current=payload.current,
        peak=payload.peak,
        actor_role=actor.role,
        seed_tier=payload.seed_tier,
        seed_division=payload.seed_division,
        changed_by=actor.display_name,
        reason=payload.reason,
        sub_role=payload.sub_role,
        recommendation=payload.recommendation,
        peak_achieved_season=payload.peak_achieved_season,
    )


@router.post("/{player_id}/refresh", response_model=Player)
def refresh_player(
    server_id: int,
    player_id: int,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Player:
    player, _message = _service(server_id, db).refresh_from_riot(player_id, actor.role)
    return player


@router.put("/{player_id}", response_model=Player)
def update_player(
    server_id: int,
    player_id: int,
    payload: Player,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Player:
    payload.id = player_id
    return _service(server_id, db).update_player(payload, actor.role)


@router.post("/{player_id}/deactivate", response_model=Player)
def deactivate_player(
    server_id: int, player_id: int, db: Session = Depends(get_db), actor: ServerMembership = Depends(get_actor)
) -> Player:
    return _service(server_id, db).deactivate_player(player_id, actor.role)


@router.post("/{player_id}/reactivate", response_model=Player)
def reactivate_player(
    server_id: int, player_id: int, db: Session = Depends(get_db), actor: ServerMembership = Depends(get_actor)
) -> Player:
    return _service(server_id, db).reactivate_player(player_id, actor.role)


@router.post("/{player_id}/seed-rating", response_model=Player)
def set_seed_rating(
    server_id: int,
    player_id: int,
    payload: SeedRatingRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Player:
    return _service(server_id, db).set_seed_rating(
        player_id, payload.seed_tier, actor.display_name, actor.role, payload.seed_division, payload.reason
    )


@router.post("/{player_id}/internal-rating", response_model=Player)
def override_internal_rating(
    server_id: int,
    player_id: int,
    payload: InternalRatingOverrideRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Player:
    return _service(server_id, db).override_internal_rating(
        player_id, payload.new_internal_rating, actor.role, actor.display_name, payload.reason
    )


@router.get("/{player_id}/season-rank-history", response_model=list[PlayerSeasonRank])
def season_rank_history(server_id: int, player_id: int, db: Session = Depends(get_db)) -> list[PlayerSeasonRank]:
    return _service(server_id, db).season_rank_history(player_id)


@router.get("/{player_id}/internal-rating-history", response_model=list[InternalRatingChange])
def internal_rating_history(
    server_id: int, player_id: int, db: Session = Depends(get_db)
) -> list[InternalRatingChange]:
    return _service(server_id, db).internal_rating_history(player_id)


@router.get("/{player_id}/seed-rating-history", response_model=list[SeedRatingChange])
def seed_rating_history(server_id: int, player_id: int, db: Session = Depends(get_db)) -> list[SeedRatingChange]:
    return _service(server_id, db).seed_rating_history(player_id)


@router.get("/{player_id}/infer-position", response_model=Optional[RoleRecommendation])
def infer_position(server_id: int, player_id: int, db: Session = Depends(get_db)) -> Optional[RoleRecommendation]:
    service = _service(server_id, db)
    player = service.get_player(player_id)
    if not player.puuid:
        return None
    return service.infer_position(player.puuid)


class PeakTierResponse(BaseModel):
    tier_snapshot: TierSnapshot
    season: str


@router.get("/lookup/peak-tier", response_model=Optional[PeakTierResponse])
def resolve_peak_tier(
    server_id: int,
    game_name: str,
    tag_line: str,
    current_tier: Optional[Tier] = None,
    current_division: Optional[Division] = None,
    current_lp: Optional[int] = None,
    db: Session = Depends(get_db),
) -> Optional[PeakTierResponse]:
    current = (
        TierSnapshot(current_tier, current_division, current_lp)
        if current_tier is not None and current_division is not None and current_lp is not None
        else None
    )
    result = _service(server_id, db).resolve_peak_tier(game_name, tag_line, current)
    if result is None:
        return None
    snapshot, season = result
    return PeakTierResponse(tier_snapshot=snapshot, season=season)
