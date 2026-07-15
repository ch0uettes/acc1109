from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DecisionLogEntity(Base):
    """One team-generation decision, captured at the moment an operator
    saves a combo. `player_ids`/`recommendations` are JSON blobs (not
    normalized tables) since this is a write-once audit snapshot, never
    queried by individual field - the whole point is "what did the AI
    see and choose, verbatim," not a live-editable record. Foundation
    for v2.0's AI Learning Engine: `chosen_rank` vs "always 1" (the AI's
    own top pick) is the Human Feedback signal - when an operator picks
    a lower-ranked combo, that's a training signal the model was wrong
    about what "best" means for this community."""

    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    strategy_name: Mapped[str]
    player_ids: Mapped[list] = mapped_column(JSON)
    recommendations: Mapped[list] = mapped_column(JSON)
    chosen_rank: Mapped[int]
    chosen_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    reason: Mapped[Optional[str]] = mapped_column(nullable=True)

    # Added for the v1.0 ExecutionContext/reproducibility work - all
    # nullable since rows written before this migration have none of
    # these (see scripts/migrate_2026_v1_schema.py and
    # DecisionLogRepository._to_domain()'s None-coalescing).
    execution_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    search_policy_name: Mapped[Optional[str]] = mapped_column(nullable=True)
    player_snapshot: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    search_statistics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    version_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    execution_time_seconds: Mapped[Optional[float]] = mapped_column(nullable=True)
    candidate_count: Mapped[Optional[int]] = mapped_column(nullable=True)
