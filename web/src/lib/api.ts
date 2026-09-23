// Thin typed client over the FastAPI backend (app/api/*). Mirrors the
// pydantic domain models field-for-field rather than redefining a
// separate DTO shape, since the backend already serializes them as-is.

export type Tier =
  | "IRON"
  | "BRONZE"
  | "SILVER"
  | "GOLD"
  | "PLATINUM"
  | "EMERALD"
  | "DIAMOND"
  | "MASTER"
  | "UNRANKED";
export type Division = "I" | "II" | "III" | "IV";
export type Position = "TOP" | "JUNGLE" | "MID" | "ADC" | "SUPPORT";
export type RatingSource = "CURRENT_SEASON" | "MANUAL" | "SEED";
export type Role = "PLATFORM_ADMIN" | "OWNER" | "SERVER_ADMIN" | "MODERATOR" | "PLAYER";

export interface Player {
  id: number;
  server_id: number | null;
  discord_id: string | null;
  puuid: string | null;
  nickname: string;
  tier: Tier;
  division: Division;
  lp: number;
  peak_tier: Tier | null;
  peak_division: Division | null;
  peak_lp: number | null;
  peak_achieved_season: string | null;
  official_rating: number | null;
  seed_rating: number | null;
  rating_source: RatingSource;
  calibration_mode: boolean;
  internal_rating: number;
  main_role: Position;
  sub_role: Position | null;
  recent_form: number;
  champion_pool: string[];
  confidence: number;
  games_played: number;
  is_active: boolean;
}

export interface Server {
  id: number;
  name: string;
  discord_guild_id: string | null;
  created_at: string;
}

export interface ServerMembership {
  id: number;
  server_id: number;
  display_name: string;
  discord_id: string | null;
  role: Role;
  created_at: string;
}

export interface RolePreference {
  main: Position;
  sub: Position | null;
}

export interface TeamSlot {
  position: Position;
  player: Player;
  role_penalty: number;
  role_source: "main" | "sub" | "other";
}

export interface Team {
  index: number;
  players: Player[];
  slots: TeamSlot[] | null;
}

export interface FeatureContribution {
  name: string;
  raw: number;
  normalized: number;
  weight: number;
  contribution: number;
  contribution_pct: number;
}

export interface BalanceResult {
  teams: Team[];
  cost: number;
  cost_breakdown: Record<string, number>;
  contributions: FeatureContribution[];
  iterations: number;
}

export interface GenerateTeamsResponse {
  results: BalanceResult[];
  decision_log_draft: unknown;
}

export interface SavedRosterEntry {
  position: Position;
  player: Player | null;
}

export interface SavedTeam {
  index: number;
  entries: SavedRosterEntry[];
}

export type Strategy = "competitive" | "comfort" | "stable";

export interface OCRPlayerRow {
  raw_name: string;
  matched_player_id: number | null;
  champion: string;
  team_index: number;
  kills: number;
  deaths: number;
  assists: number;
  cs: number;
  gold: number;
  damage: number;
  vision_score: number;
}

export interface MatchResultData {
  participants: OCRPlayerRow[];
  winning_team_index: number | null;
  raw_text: string;
}

export interface ContributionScore {
  player_id: number;
  combat: number;
  vision: number;
  objective: number;
  economy: number;
  death_penalty: number;
}

export interface MatchPlayerResult {
  player_id: number;
  team_index: number;
  position: Position;
  contribution: ContributionScore;
}

export interface Match {
  id: number | null;
  server_id: number | null;
  played_at: string;
  participants: MatchPlayerResult[];
  winning_team_index: number;
  ai_mvp_player_id: number | null;
  user_mvp_player_id: number | null;
  note: string | null;
}

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; actorName?: string } = {}
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.actorName) headers["X-Actor-Name"] = options.actorName;

  const res = await fetch(`${BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, detail.detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listServers: () => request<Server[]>("/servers"),
  createServer: (name: string, ownerDisplayName: string) =>
    request<Server>("/servers", {
      method: "POST",
      body: { name, owner_display_name: ownerDisplayName },
    }),
  joinServer: (serverId: number, displayName: string) =>
    request<ServerMembership>(`/servers/${serverId}/members`, {
      method: "POST",
      body: { display_name: displayName },
    }),

  listPlayers: (serverId: number, includeInactive = false) =>
    request<Player[]>(`/servers/${serverId}/players?include_inactive=${includeInactive}`),
  createPlayer: (
    serverId: number,
    actorName: string,
    payload: {
      nickname: string;
      tier: Tier;
      division?: Division;
      lp?: number;
      main_role: Position;
      sub_role?: Position | null;
    }
  ) => request<Player>(`/servers/${serverId}/players`, { method: "POST", body: payload, actorName }),
  deactivatePlayer: (serverId: number, actorName: string, playerId: number) =>
    request<Player>(`/servers/${serverId}/players/${playerId}/deactivate`, {
      method: "POST",
      actorName,
    }),
  reactivatePlayer: (serverId: number, actorName: string, playerId: number) =>
    request<Player>(`/servers/${serverId}/players/${playerId}/reactivate`, {
      method: "POST",
      actorName,
    }),
  setSeedRating: (
    serverId: number,
    actorName: string,
    playerId: number,
    seedTier: Tier,
    seedDivision: Division = "III"
  ) =>
    request<Player>(`/servers/${serverId}/players/${playerId}/seed-rating`, {
      method: "POST",
      body: { seed_tier: seedTier, seed_division: seedDivision },
      actorName,
    }),

  generateTeams: (
    serverId: number,
    payload: {
      player_ids: number[];
      overrides?: { player_id: number; match_override?: RolePreference | null; enforce_fixed_role?: boolean }[];
      k?: number;
      strategy?: Strategy;
    }
  ) => request<GenerateTeamsResponse>(`/servers/${serverId}/teams/generate`, { method: "POST", body: payload }),
  saveTeams: (
    serverId: number,
    actorName: string,
    payload: { teams: Team[]; decision_log_draft?: unknown; chosen_rank?: number; reason?: string | null }
  ) =>
    request<number[]>(`/servers/${serverId}/teams/save`, {
      method: "POST",
      body: payload,
      actorName,
    }),
  listSavedRuns: (serverId: number, limit = 20) =>
    request<string[]>(`/servers/${serverId}/teams/runs?limit=${limit}`),
  loadSavedRun: (serverId: number, generatedAt: string) =>
    request<SavedTeam[]>(`/servers/${serverId}/teams/runs/${encodeURIComponent(generatedAt)}`),
  savedRunExportUrl: (serverId: number, generatedAt: string, format: "txt" | "xlsx") =>
    `${BASE_URL}/servers/${serverId}/teams/runs/${encodeURIComponent(generatedAt)}/export.${format}`,

  recordMatch: (
    serverId: number,
    actorName: string,
    payload: {
      teams: Team[];
      winning_team_index: number;
      note?: string | null;
      match_stats_by_player_id?: Record<
        number,
        { kills: number; deaths: number; assists: number; cs: number; gold: number; damage: number; vision_score: number }
      >;
    }
  ) => request<Match>(`/servers/${serverId}/matches`, { method: "POST", body: payload, actorName }),

  extractMatchResult: async (
    serverId: number,
    file: File,
    knownNicknames: string[]
  ): Promise<MatchResultData> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(
      `${BASE_URL}/ocr/match-result?known_nicknames=${encodeURIComponent(knownNicknames.join(","))}`,
      { method: "POST", body: form }
    );
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, detail.detail ?? res.statusText);
    }
    return res.json();
  },

  mergeDetailStats: async (
    file: File,
    participants: OCRPlayerRow[]
  ): Promise<{ participants: OCRPlayerRow[]; matched_count: number; ambiguous_names: string[] }> => {
    const form = new FormData();
    form.append("file", file);
    form.append("participants", JSON.stringify(participants));
    const res = await fetch(`${BASE_URL}/ocr/detail-stats/merge`, { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, detail.detail ?? res.statusText);
    }
    return res.json();
  },

  listPendingVotes: (serverId: number) => request<Match[]>(`/servers/${serverId}/matches/pending-votes`),
  castVote: (serverId: number, actorName: string, matchId: number, voterPlayerId: number, votedPlayerId: number) =>
    request(`/servers/${serverId}/matches/${matchId}/votes`, {
      method: "POST",
      body: { voter_player_id: voterPlayerId, voted_player_id: votedPlayerId },
      actorName,
    }),
  tallyVote: (serverId: number, matchId: number) =>
    request<number | null>(`/servers/${serverId}/matches/${matchId}/votes/tally`),
  setUserMvp: (serverId: number, actorName: string, matchId: number, playerId: number) =>
    request<void>(`/servers/${serverId}/matches/${matchId}/user-mvp`, {
      method: "POST",
      body: { player_id: playerId },
      actorName,
    }),

  leaderboard: (serverId: number) => request<Player[]>(`/servers/${serverId}/stats/leaderboard`),
  aiMvpAccuracy: (serverId: number) => request<number>(`/servers/${serverId}/stats/ai-mvp-accuracy`),
};
