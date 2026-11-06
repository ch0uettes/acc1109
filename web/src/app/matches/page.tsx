"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, Match, MatchResultData, OCRPlayerRow, Player, Position, SavedTeam } from "@/lib/api";
import { POSITION_ORDER } from "@/lib/playerTable";
import { useSession } from "@/lib/session";
import { formatUtc, parseUtc } from "@/lib/time";

const STAT_FIELDS = ["kills", "deaths", "assists", "cs", "gold", "damage", "vision_score"] as const;
const STAT_LABELS: Record<(typeof STAT_FIELDS)[number], string> = {
  kills: "K",
  deaths: "D",
  assists: "A",
  cs: "CS",
  gold: "골드",
  damage: "딜량",
  vision_score: "시야",
};

interface RunPlayer {
  player: Player;
  teamIndex: number;
  position: Position;
}

function sameInstant(a: string, b: string): boolean {
  return parseUtc(a).getTime() === parseUtc(b).getTime();
}

function normalizeName(name: string): string {
  return name.replace(/\s+/g, "").toLowerCase();
}

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

export default function MatchesPage() {
  const router = useRouter();
  const { serverId, actorName, isAdmin, loaded } = useSession();

  const [runs, setRuns] = useState<string[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [runTeams, setRunTeams] = useState<SavedTeam[] | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [players, setPlayers] = useState<Player[]>([]);

  const [file, setFile] = useState<File | null>(null);
  const [detailFile, setDetailFile] = useState<File | null>(null);
  const [ocrResult, setOcrResult] = useState<MatchResultData | null>(null);
  const [winnerIndex, setWinnerIndex] = useState<number | null>(null);
  const [note, setNote] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    if (!serverId) return;
    api.listSavedRuns(serverId).then(setRuns).catch((e) => setError(errorText(e)));
    api.listMatches(serverId).then(setMatches).catch((e) => setError(errorText(e)));
    api.listPlayers(serverId, true).then(setPlayers).catch(() => undefined);
  }, [serverId]);

  useEffect(() => {
    if (loaded && (!serverId || !actorName)) {
      router.push("/");
      return;
    }
    refresh();
  }, [loaded, serverId, actorName, router, refresh]);

  useEffect(() => {
    if (runs.length > 0 && !runs.some((r) => r === selectedRun)) setSelectedRun(runs[0]);
  }, [runs, selectedRun]);

  useEffect(() => {
    setOcrResult(null);
    setWinnerIndex(null);
    if (!serverId || !selectedRun) {
      setRunTeams(null);
      return;
    }
    api
      .loadSavedRun(serverId, selectedRun)
      .then(setRunTeams)
      .catch((e) => setError(errorText(e)));
  }, [serverId, selectedRun]);

  const playersById = useMemo(() => new Map(players.map((p) => [p.id, p])), [players]);
  const nameOf = (id: number | null | undefined) => (id != null ? playersById.get(id)?.nickname ?? `#${id}` : "-");

  const recordedMatchByRun = (run: string) => matches.find((m) => m.team_run_at && sameInstant(m.team_run_at, run));
  const selectedRecorded = selectedRun ? recordedMatchByRun(selectedRun) : undefined;

  const runPlayers: RunPlayer[] = useMemo(
    () =>
      (runTeams ?? []).flatMap((team) =>
        team.entries
          .filter((e) => e.player)
          .map((e) => ({ player: e.player as Player, teamIndex: team.index, position: e.position }))
      ),
    [runTeams]
  );

  function guessPlayer(rawName: string): number | null {
    const key = normalizeName(rawName);
    if (!key) return null;
    const hit = runPlayers.find(
      (rp) =>
        normalizeName(rp.player.nickname) === key ||
        (rp.player.riot_game_name && normalizeName(rp.player.riot_game_name) === key)
    );
    return hit ? hit.player.id : null;
  }

  async function handleAnalyze() {
    if (!serverId || !file) return;
    setBusy(true);
    setError(null);
    try {
      const knownNames = runPlayers.flatMap((rp) =>
        rp.player.riot_game_name ? [rp.player.nickname, rp.player.riot_game_name] : [rp.player.nickname]
      );
      const result = await api.extractMatchResult(serverId, file, knownNames);
      setOcrResult({
        ...result,
        participants: result.participants.map((row) => ({ ...row, matched_player_id: guessPlayer(row.raw_name) })),
      });
      if (result.winning_team_index !== null) setWinnerIndex(result.winning_team_index);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleAnalyzeDetail() {
    if (!detailFile || !ocrResult) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.mergeDetailStats(detailFile, ocrResult.participants);
      setOcrResult({ ...ocrResult, participants: res.participants });
      setInfo(
        `${res.matched_count}/${res.participants.length}명만 KDA로 매칭됐습니다.` +
          (res.ambiguous_names.length ? ` (겹치는 KDA: ${res.ambiguous_names.join(", ")})` : "")
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  function updateRow(index: number, patch: Partial<OCRPlayerRow>) {
    if (!ocrResult) return;
    const participants = [...ocrResult.participants];
    participants[index] = { ...participants[index], ...patch };
    setOcrResult({ ...ocrResult, participants });
  }

  const assignedIds = (ocrResult?.participants ?? []).map((r) => r.matched_player_id).filter((id) => id != null);
  const duplicateIds = new Set(assignedIds.filter((id, i) => assignedIds.indexOf(id) !== i));
  const unmatchedRows = (ocrResult?.participants ?? []).filter((r) => r.matched_player_id == null).length;

  async function handleRecord() {
    if (!serverId || !selectedRun || winnerIndex === null) return;
    if (duplicateIds.size > 0) {
      setError("같은 참가자가 두 줄에 지정되어 있습니다. 표에서 참가자를 다시 골라주세요.");
      return;
    }
    const statsByPlayerId: Record<number, Record<(typeof STAT_FIELDS)[number], number>> = {};
    for (const row of ocrResult?.participants ?? []) {
      if (row.matched_player_id == null) continue;
      statsByPlayerId[row.matched_player_id] = Object.fromEntries(STAT_FIELDS.map((f) => [f, row[f]])) as Record<
        (typeof STAT_FIELDS)[number],
        number
      >;
    }
    if (ocrResult) {
      const missing = runPlayers.filter((rp) => !(rp.player.id in statsByPlayerId)).map((rp) => rp.player.nickname);
      if (
        missing.length > 0 &&
        !window.confirm(`${missing.join(", ")} - ${missing.length}명은 스탯 없이 저장됩니다 (승패만 반영). 계속할까요?`)
      ) {
        return;
      }
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const match = await api.recordMatch(serverId, {
        team_run_at: selectedRun,
        winning_team_index: winnerIndex,
        note: note || null,
        match_stats_by_player_id: statsByPlayerId,
      });
      setInfo(`경기를 저장했습니다. AI MVP: ${nameOf(match.ai_mvp_player_id)}`);
      setOcrResult(null);
      setFile(null);
      setDetailFile(null);
      setNote("");
      setWinnerIndex(null);
      refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(match: Match) {
    if (!serverId || match.id == null) return;
    const message = match.revertible
      ? `경기 #${match.id}을(를) 삭제하면 참가자 ${match.participants.length}명의 레이팅과 게임 수가 이 경기 전으로 돌아가고, 투표도 함께 삭제됩니다. 삭제할까요?`
      : `경기 #${match.id}은(는) 레이팅 변화 기록이 없는 이전 경기라, 레이팅은 그대로 두고 기록과 투표만 삭제합니다. 삭제할까요?`;
    if (!window.confirm(message)) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await api.deleteMatch(serverId, match.id);
      setInfo(
        res.ratings_reverted
          ? `경기 #${match.id}을(를) 삭제하고 레이팅을 되돌렸습니다. 같은 팀으로 다시 저장할 수 있습니다.`
          : `경기 #${match.id} 기록을 삭제했습니다 (레이팅은 그대로).`
      );
      refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (!loaded || !serverId || !actorName) return null;

  return (
    <div>
      <h1>경기 저장</h1>
      {error && <p className="error">{error}</p>}
      {info && <p className="muted">{info}</p>}

      {isAdmin ? (
        runs.length === 0 ? (
          <div className="card">
            <p className="muted">저장된 팀이 없습니다. 먼저 &apos;팀 생성&apos;에서 팀을 만들고 저장해주세요.</p>
          </div>
        ) : (
          <>
            <div className="card">
              <h3>어떤 팀으로 경기했나요?</h3>
              <div className="row">
                <select value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)}>
                  {runs.map((run) => (
                    <option key={run} value={run}>
                      {formatUtc(run, true)}
                      {recordedMatchByRun(run) ? " · 이미 저장됨" : ""}
                    </option>
                  ))}
                </select>
              </div>
              {selectedRecorded && (
                <p className="error">
                  이 팀으로는 이미 경기 #{selectedRecorded.id}이(가) 저장되어 있습니다. 결과를 고치려면 아래 최근 경기에서
                  삭제한 뒤 다시 저장하세요.
                </p>
              )}
              {runTeams && (
                <div className="row" style={{ alignItems: "flex-start", marginTop: 12 }}>
                  {runTeams.map((team) => (
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

            {!selectedRecorded && runTeams && (
              <>
                <div className="card">
                  <h3>결과창 스크린샷으로 스탯 넣기 (선택)</h3>
                  <div className="row">
                    <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                    <button onClick={handleAnalyze} disabled={busy || !file}>
                      스크린샷 분석
                    </button>
                  </div>

                  {ocrResult && (
                    <>
                      <p className="muted" style={{ marginTop: 8 }}>
                        줄마다 &apos;참가자&apos;가 맞는지 확인하세요.{" "}
                        {unmatchedRows > 0 && (
                          <span className="error">{unmatchedRows}줄은 참가자를 찾지 못했습니다 (빨간 줄).</span>
                        )}
                      </p>
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>화면 이름</th>
                              <th>참가자</th>
                              {STAT_FIELDS.map((f) => (
                                <th key={f}>{STAT_LABELS[f]}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {ocrResult.participants.map((row, i) => {
                              const unmatched = row.matched_player_id == null;
                              const duplicate = row.matched_player_id != null && duplicateIds.has(row.matched_player_id);
                              return (
                                <tr
                                  key={i}
                                  style={unmatched ? { background: "rgba(229, 85, 90, 0.12)" } : undefined}
                                >
                                  <td>
                                    {row.raw_name}
                                    <div className="muted">{row.team_index + 1}팀</div>
                                  </td>
                                  <td>
                                    <select
                                      aria-label={`${row.raw_name} 참가자`}
                                      value={row.matched_player_id ?? ""}
                                      onChange={(e) =>
                                        updateRow(i, {
                                          matched_player_id: e.target.value ? Number(e.target.value) : null,
                                        })
                                      }
                                    >
                                      <option value="">선택 안 함</option>
                                      {runPlayers.map((rp) => (
                                        <option key={rp.player.id} value={rp.player.id}>
                                          {rp.teamIndex + 1}팀 {rp.position} · {rp.player.nickname}
                                        </option>
                                      ))}
                                    </select>
                                    {duplicate && <div className="error">다른 줄과 중복</div>}
                                  </td>
                                  {STAT_FIELDS.map((field) => (
                                    <td key={field}>
                                      <input
                                        type="number"
                                        value={row[field]}
                                        onChange={(e) => updateRow(i, { [field]: Number(e.target.value) })}
                                        style={{ width: 70 }}
                                      />
                                    </td>
                                  ))}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>

                      <div className="row" style={{ marginTop: 8 }}>
                        <input
                          type="file"
                          accept="image/*"
                          onChange={(e) => setDetailFile(e.target.files?.[0] ?? null)}
                        />
                        <button className="secondary" onClick={handleAnalyzeDetail} disabled={busy || !detailFile}>
                          상세 스탯 분석 (선택)
                        </button>
                      </div>
                    </>
                  )}
                </div>

                <div className="card">
                  <div className="row">
                    <label htmlFor="winner">승리 팀</label>
                    <select
                      id="winner"
                      value={winnerIndex ?? ""}
                      onChange={(e) => setWinnerIndex(e.target.value === "" ? null : Number(e.target.value))}
                    >
                      <option value="">승리 팀 선택</option>
                      {(runTeams ?? []).map((team) => (
                        <option key={team.index} value={team.index}>
                          {team.index + 1}팀
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="row" style={{ marginTop: 8 }}>
                    <input
                      placeholder="비고"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      style={{ flex: 1 }}
                    />
                  </div>
                  <div className="row" style={{ marginTop: 12 }}>
                    <button onClick={handleRecord} disabled={busy || winnerIndex === null}>
                      경기 결과 저장
                    </button>
                  </div>
                </div>
              </>
            )}
          </>
        )
      ) : (
        <div className="card">
          <p className="muted">경기 저장은 관리자만 할 수 있습니다. 최근 경기 기록은 아래에서 볼 수 있습니다.</p>
        </div>
      )}

      <div className="card">
        <h3>최근 경기</h3>
        {matches.length === 0 ? (
          <p className="muted">아직 저장된 경기가 없습니다.</p>
        ) : (
          matches.map((match) => {
            const teams = [...new Set(match.participants.map((p) => p.team_index))].sort();
            return (
              <div
                key={match.id ?? match.played_at}
                style={{ borderTop: "1px solid var(--border)", padding: "12px 0" }}
              >
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <strong>
                    #{match.id} · {formatUtc(match.played_at)} · {match.winning_team_index + 1}팀 승
                  </strong>
                  {isAdmin && (
                    <button className="danger" onClick={() => handleDelete(match)} disabled={busy}>
                      삭제
                    </button>
                  )}
                </div>
                <div className="row" style={{ alignItems: "flex-start", marginTop: 6 }}>
                  {teams.map((t) => (
                    <div key={t} style={{ minWidth: 160 }}>
                      <span className="muted">
                        {t + 1}팀{t === match.winning_team_index ? " (승)" : ""}:{" "}
                      </span>
                      {match.participants
                        .filter((p) => p.team_index === t)
                        .sort((a, b) => POSITION_ORDER.indexOf(a.position) - POSITION_ORDER.indexOf(b.position))
                        .map((p) => nameOf(p.player_id))
                        .join(", ")}
                    </div>
                  ))}
                </div>
                <div className="muted" style={{ marginTop: 4 }}>
                  AI MVP {nameOf(match.ai_mvp_player_id)} · User MVP{" "}
                  {match.user_mvp_player_id != null ? nameOf(match.user_mvp_player_id) : "투표 중"}
                  {match.note ? ` · ${match.note}` : ""}
                  {!match.revertible && " · 이전 기록 (삭제해도 레이팅은 그대로)"}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
