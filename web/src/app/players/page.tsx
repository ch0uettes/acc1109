"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, Division, Player, Position, Tier } from "@/lib/api";
import { useSession } from "@/lib/session";

const TIERS: Tier[] = [
  "IRON",
  "BRONZE",
  "SILVER",
  "GOLD",
  "PLATINUM",
  "EMERALD",
  "DIAMOND",
  "MASTER",
  "UNRANKED",
];
const DIVISIONS: Division[] = ["I", "II", "III", "IV"];
const POSITIONS: Position[] = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"];

export default function PlayersPage() {
  const router = useRouter();
  const { serverId, actorName, loaded } = useSession();

  const [players, setPlayers] = useState<Player[]>([]);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Manual-entry form state - mirrors player_page.py's "수동 입력" tab.
  const [nickname, setNickname] = useState("");
  const [tier, setTier] = useState<Tier>("GOLD");
  const [division, setDivision] = useState<Division>("IV");
  const [lp, setLp] = useState(0);
  const [mainRole, setMainRole] = useState<Position>("TOP");
  const [subRole, setSubRole] = useState<Position | "">("");

  const refresh = useCallback(() => {
    if (!serverId) return;
    api
      .listPlayers(serverId, includeInactive)
      .then(setPlayers)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [serverId, includeInactive]);

  useEffect(() => {
    if (loaded && (!serverId || !actorName)) {
      router.push("/");
      return;
    }
    refresh();
  }, [loaded, serverId, actorName, router, refresh]);

  async function handleCreate() {
    if (!serverId || !actorName || !nickname) return;
    setBusy(true);
    setError(null);
    try {
      await api.createPlayer(serverId, actorName, {
        nickname,
        tier,
        division,
        lp,
        main_role: mainRole,
        sub_role: subRole || null,
      });
      setNickname("");
      setLp(0);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleActive(player: Player) {
    if (!serverId || !actorName) return;
    setBusy(true);
    setError(null);
    try {
      if (player.is_active) {
        await api.deactivatePlayer(serverId, actorName, player.id);
      } else {
        await api.reactivatePlayer(serverId, actorName, player.id);
      }
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!loaded || !serverId || !actorName) return null;

  return (
    <div>
      <h1>참가자 관리</h1>
      <p className="muted">
        서버 #{serverId} · {actorName}
      </p>
      {error && <p className="error">{error}</p>}

      <div className="card">
        <h3>수동 입력</h3>
        <div className="row">
          <input
            placeholder="닉네임"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
          />
          <select value={tier} onChange={(e) => setTier(e.target.value as Tier)}>
            {TIERS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select value={division} onChange={(e) => setDivision(e.target.value as Division)}>
            {DIVISIONS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <input
            type="number"
            placeholder="LP"
            value={lp}
            min={0}
            max={3000}
            onChange={(e) => setLp(Number(e.target.value))}
            style={{ width: 80 }}
          />
          <select value={mainRole} onChange={(e) => setMainRole(e.target.value as Position)}>
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <select value={subRole} onChange={(e) => setSubRole(e.target.value as Position | "")}>
            <option value="">부 포지션 없음</option>
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <button onClick={handleCreate} disabled={busy || !nickname}>
            등록
          </button>
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h3 style={{ margin: 0 }}>참가자 목록 ({players.length})</h3>
          <label className="row" style={{ gap: 4 }}>
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
            />
            비활성 포함
          </label>
        </div>
        <table>
          <thead>
            <tr>
              <th>닉네임</th>
              <th>티어</th>
              <th>포지션</th>
              <th>Final Rating</th>
              <th>출처</th>
              <th>상태</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.id} style={{ opacity: p.is_active ? 1 : 0.5 }}>
                <td>{p.nickname}</td>
                <td>
                  {p.tier} {p.division !== "IV" || p.tier !== "UNRANKED" ? p.division : ""} {p.lp}LP
                </td>
                <td>
                  {p.main_role}
                  {p.sub_role ? ` / ${p.sub_role}` : ""}
                </td>
                <td>{(p.official_rating ?? p.seed_rating ?? 0).toFixed(0)}</td>
                <td>
                  <span className="badge">{p.rating_source}</span>
                </td>
                <td>{p.is_active ? "활성" : "비활성"}</td>
                <td>
                  <button
                    className="secondary"
                    onClick={() => handleToggleActive(p)}
                    disabled={busy}
                  >
                    {p.is_active ? "비활성화" : "재활성화"}
                  </button>
                </td>
              </tr>
            ))}
            {players.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  등록된 참가자가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
