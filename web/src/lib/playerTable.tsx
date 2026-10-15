"use client";

// Shared sort/search for the player tables on 참가자 관리 and 팀 생성.
import { useMemo, useState } from "react";
import type { Division, Player, Position, Tier } from "./api";

const TIER_ORDER: Tier[] = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER"];
const DIVISION_ORDER: Division[] = ["IV", "III", "II", "I"];
export const POSITION_ORDER: Position[] = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"];

export function displayedRating(p: Player): number {
  return p.official_rating ?? p.seed_rating ?? 0;
}

// Same rule as the backend's tier_strength (app/models/team.py): tier,
// then division (I best), then LP; UNRANKED below Iron; ties by rating.
export function tierStrength(p: Player): number[] {
  const tier = TIER_ORDER.indexOf(p.tier);
  if (tier < 0) return [-1, 0, 0, displayedRating(p)];
  return [tier, DIVISION_ORDER.indexOf(p.division), p.lp, displayedRating(p)];
}

function compareTuples(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const diff = (a[i] ?? 0) - (b[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

export function captainId(players: Player[]): number | null {
  if (players.length === 0) return null;
  return players.reduce((best, p) => (compareTuples(tierStrength(p), tierStrength(best)) > 0 ? p : best)).id;
}

export type SortKey = "nickname" | "tier" | "position" | "rating" | "source" | "status";

const COMPARATORS: Record<SortKey, (a: Player, b: Player) => number> = {
  nickname: (a, b) => a.nickname.localeCompare(b.nickname, "ko"),
  tier: (a, b) => compareTuples(tierStrength(a), tierStrength(b)),
  position: (a, b) => POSITION_ORDER.indexOf(a.main_role) - POSITION_ORDER.indexOf(b.main_role),
  rating: (a, b) => displayedRating(a) - displayedRating(b),
  source: (a, b) => a.rating_source.localeCompare(b.rating_source),
  status: (a, b) => Number(b.is_active) - Number(a.is_active),
};

export function usePlayerTable(players: Player[]) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [descending, setDescending] = useState(false);
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q ? players.filter((p) => p.nickname.toLowerCase().includes(q)) : players;
    if (!sortKey) return filtered;
    const sorted = [...filtered].sort(COMPARATORS[sortKey]);
    return descending ? sorted.reverse() : sorted;
  }, [players, query, sortKey, descending]);

  // First click sorts ascending, second descending, third clears.
  function toggleSort(key: SortKey) {
    if (sortKey !== key) {
      setSortKey(key);
      setDescending(false);
    } else if (!descending) {
      setDescending(true);
    } else {
      setSortKey(null);
      setDescending(false);
    }
  }

  function sortTh(sortBy: SortKey, label: string) {
    const active = sortKey === sortBy;
    return (
      <th onClick={() => toggleSort(sortBy)} style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}>
        {label} <span className="muted">{active ? (descending ? "▼" : "▲") : "↕"}</span>
      </th>
    );
  }

  const searchInput = (
    <input
      type="search"
      placeholder="닉네임 검색"
      value={query}
      onChange={(e) => setQuery(e.target.value)}
      style={{ minWidth: 180 }}
    />
  );

  return { rows, sortTh, searchInput, query };
}
