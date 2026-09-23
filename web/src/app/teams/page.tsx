"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  ApiError,
  BalanceResult,
  Player,
  Position,
  RolePreference,
  SavedTeam,
  Strategy,
} from "@/lib/api";
import { useSession } from "@/lib/session";

const POSITIONS: Position[] = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"];

const STRATEGY_LABELS: Record<Strategy, string> = {
  competitive: "Competitive - 라인전 공정성 최우선",
  comfort: "Comfort - 원하는 포지션 최우선",
  stable: "Stable (기본) - 전체 안정성 최우선",
};

interface OverrideState {
  main: Position;
  sub: Position | "";
  enforce_fixed_role: boolean;
}

export default function TeamsPage() {
  const router = useRouter();
  const { serverId, actorName, loaded } = useSession();

  const [players, setPlayers] = useState<Player[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [overrides, setOverrides] = useState<Record<number, OverrideState>>({});
  const [strategy, setStrategy] = useState<Strategy>("stable");

  const [generateResponse, setGenerateResponse] = useState<{
    results: BalanceResult[];
    decision_log_draft: unknown;
  } | null>(null);
  const [comboIndex, setComboIndex] = useState(0);
  const [reason, setReason] = useState("");

  const [savedRuns, setSavedRuns] = useState<string[]>([]);
  const [selectedRun, setSelectedRun] = useState<string>("");
  const [savedTeams, setSavedTeams] = useState<SavedTeam[] | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshPlayers = useCallback(() => {
    if (!serverId) return;
    api.listPlayers(serverId).then(setPlayers).catch((e) => setError(String(e)));
  }, [serverId]);

  const refreshRuns = useCallback(() => {
    if (!serverId) return;
    api
      .listSavedRuns(serverId)
      .then((runs) => {
        setSavedRuns(runs);
        if (runs.length && !selectedRun) setSelectedRun(runs[0]);
      })
      .catch(() => undefined);
  }, [serverId, selectedRun]);

  useEffect(() => {
    if (loaded && (!serverId || !actorName)) {
      router.push("/");
      return;
    }
    refreshPlayers();
    refreshRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, serverId, actorName, router]);

  useEffect(() => {
    if (!serverId || !selectedRun) {
      setSavedTeams(null);
      return;
    }
    api
      .loadSavedRun(serverId, selectedRun)
      .then(setSavedTeams)
      .catch(() => setSavedTeams(null));
  }, [serverId, selectedRun]);

  function toggleSelected(playerId: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(playerId)) next.delete(playerId);
      else next.add(playerId);
      return next;
    });
  }

  function toggleOverride(playerId: number, enabled: boolean) {
    setOverrides((prev) => {
      const next = { ...prev };
      if (enabled) {
        next[playerId] = { main: "TOP", sub: "", enforce_fixed_role: true };
      } else {
        delete next[playerId];
      }
      return next;
    });
  }

  async function handleGenerate() {
    if (!serverId || selected.size === 0) return;
    setBusy(true);
    setError(null);
    setGenerateResponse(null);
    try {
      const overridePayload = Object.entries(overrides).map(([playerId, o]) => ({
        player_id: Number(playerId),
        match_override: { main: o.main, sub: o.sub || null } as RolePreference,
        enforce_fixed_role: o.enforce_fixed_role,
      }));
      const res = await api.generateTeams(serverId, {
        player_ids: Array.from(selected),
        overrides: overridePayload,
        k: 3,
        strategy,
      });
      setGenerateResponse(res);
      setComboIndex(0);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleSave() {
    if (!serverId || !actorName || !generateResponse) return;
    setBusy(true);
    setError(null);
    try {
      const chosen = generateResponse.results[comboIndex];
      await api.saveTeams(serverId, actorName, {
        teams: chosen.teams,
        decision_log_draft: generateResponse.decision_log_draft,
        chosen_rank: comboIndex + 1,
        reason: reason || null,
      });
      // Handoff to /matches - same role Streamlit's last_balance_result
      // session_state key played between team_page.py and match_page.py.
      window.localStorage.setItem("balancer.lastTeams", JSON.stringify(chosen.teams));
      setGenerateResponse(null);
      setReason("");
      refreshRuns();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!loaded || !serverId || !actorName) return null;

  const activePlayers = players.filter((p) => p.is_active);
  const selectedPlayers = activePlayers.filter((p) => selected.has(p.id));

  return (
    <div>
      <h1>팀 생성</h1>
      {error && <p className="error">{error}</p>}

      {savedRuns.length > 0 && (
        <div className="card">
          <h3>저장된 팀 불러오기</h3>
          <div className="row">
            <select value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)}>
              {savedRuns.map((ts) => (
                <option key={ts} value={ts}>
                  {new Date(ts).toLocaleString()}
                </option>
              ))}
            </select>
            {selectedRun && (
              <>
                <a href={api.savedRunExportUrl(serverId, selectedRun, "txt")}>
                  <button type="button" className="secondary">
                    TXT 다운로드
                  </button>
                </a>
                <a href={api.savedRunExportUrl(serverId, selectedRun, "xlsx")}>
                  <button type="button" className="secondary">
                    엑셀 다운로드
                  </button>
                </a>
              </>
            )}
          </div>
          {savedTeams && (
            <div className="row" style={{ alignItems: "flex-start", marginTop: 12 }}>
              {savedTeams.map((team) => (
                <div key={team.index} style={{ minWidth: 160 }}>
                  <strong>{team.index + 1}팀</strong>
                  {team.entries.map((entry, i) => (
                    <div key={i} className="muted">
                      {entry.position}: {entry.player?.nickname ?? "알 수 없음"}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h3>밸런싱 전략</h3>
        <select value={strategy} onChange={(e) => setStrategy(e.target.value as Strategy)}>
          {(Object.keys(STRATEGY_LABELS) as Strategy[]).map((s) => (
            <option key={s} value={s}>
              {STRATEGY_LABELS[s]}
            </option>
          ))}
        </select>
      </div>

      <div className="card">
        <h3>참가자 선택 (5명 단위, {selected.size}명 선택됨)</h3>
        <table>
          <thead>
            <tr>
              <th></th>
              <th>닉네임</th>
              <th>티어</th>
              <th>포지션</th>
              <th>이번 경기 전용 포지션</th>
            </tr>
          </thead>
          <tbody>
            {activePlayers.map((p) => (
              <tr key={p.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(p.id)}
                    onChange={() => toggleSelected(p.id)}
                  />
                </td>
                <td>{p.nickname}</td>
                <td>
                  {p.tier} {p.division} {p.lp}LP
                </td>
                <td>{p.main_role}</td>
                <td>
                  {selected.has(p.id) && (
                    <label className="row" style={{ gap: 4 }}>
                      <input
                        type="checkbox"
                        checked={!!overrides[p.id]}
                        onChange={(e) => toggleOverride(p.id, e.target.checked)}
                      />
                      {overrides[p.id] && (
                        <>
                          <select
                            value={overrides[p.id].main}
                            onChange={(e) =>
                              setOverrides((prev) => ({
                                ...prev,
                                [p.id]: { ...prev[p.id], main: e.target.value as Position },
                              }))
                            }
                          >
                            {POSITIONS.map((pos) => (
                              <option key={pos} value={pos}>
                                {pos}
                              </option>
                            ))}
                          </select>
                          <label className="row" style={{ gap: 2 }}>
                            <input
                              type="checkbox"
                              checked={overrides[p.id].enforce_fixed_role}
                              onChange={(e) =>
                                setOverrides((prev) => ({
                                  ...prev,
                                  [p.id]: { ...prev[p.id], enforce_fixed_role: e.target.checked },
                                }))
                              }
                            />
                            <span className="muted">고정</span>
                          </label>
                        </>
                      )}
                    </label>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={handleGenerate} disabled={busy || selected.size === 0}>
            팀 생성
          </button>
        </div>
      </div>

      {generateResponse && (
        <div className="card">
          <h3>생성 결과 (상위 {generateResponse.results.length}개)</h3>
          <div className="row">
            {generateResponse.results.map((_, i) => (
              <button
                key={i}
                className={i === comboIndex ? "" : "secondary"}
                onClick={() => setComboIndex(i)}
              >
                조합 {i + 1}위 (cost {generateResponse.results[i].cost.toFixed(1)})
              </button>
            ))}
          </div>

          <div className="row" style={{ alignItems: "flex-start", marginTop: 12 }}>
            {generateResponse.results[comboIndex].teams.map((team) => (
              <div key={team.index} style={{ minWidth: 180 }}>
                <strong>{team.index + 1}팀</strong>
                {(team.slots ?? []).map((slot, i) => (
                  <div key={i} className="muted">
                    {slot.position}: {slot.player.nickname} ({slot.player.tier})
                    {slot.role_penalty ? ` [${slot.role_source}, +${slot.role_penalty.toFixed(0)}]` : ""}
                  </div>
                ))}
                {!team.slots &&
                  team.players.map((p) => (
                    <div key={p.id} className="muted">
                      {p.nickname} ({p.tier})
                    </div>
                  ))}
              </div>
            ))}
          </div>

          {generateResponse.results[comboIndex].contributions.length > 0 && (
            <table style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Raw</th>
                  <th>Normalized</th>
                  <th>Weight</th>
                  <th>기여도</th>
                </tr>
              </thead>
              <tbody>
                {generateResponse.results[comboIndex].contributions.map((c) => (
                  <tr key={c.name}>
                    <td>{c.name}</td>
                    <td>{c.raw.toFixed(2)}</td>
                    <td>{c.normalized.toFixed(3)}</td>
                    <td>{c.weight}</td>
                    <td>{c.contribution_pct.toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="row" style={{ marginTop: 12 }}>
            <input
              placeholder="선택 사유 (선택)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{ flex: 1 }}
            />
            <button onClick={handleSave} disabled={busy}>
              팀 저장
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
