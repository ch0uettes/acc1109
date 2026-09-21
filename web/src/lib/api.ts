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
};
