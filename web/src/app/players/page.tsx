"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  ApiError,
  Division,
  OCRRiotIdRow,
  Player,
  Position,
  RoleRecommendation,
  Tier,
  TierSnapshot,
} from "@/lib/api";
import { usePlayerTable } from "@/lib/playerTable";
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
const RANKED_TIERS = TIERS.filter((t) => t !== "UNRANKED");
const DIVISIONS: Division[] = ["I", "II", "III", "IV"];
const POSITIONS: Position[] = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"];

type Tab = "manual" | "riot" | "bulk";

// Position inference is reference-only - a failure (slow match history,
// Riot rate limit) must not throw away the Riot ID lookup that already
// succeeded, so it degrades to "no recommendation" and the operator picks
// the position by hand.
async function inferPositionOrNull(serverId: number, puuid: string): Promise<RoleRecommendation | null> {
  try {
    return await api.inferPositionByPuuid(serverId, puuid);
  } catch {
    return null;
  }
}

export default function PlayersPage() {
  const router = useRouter();
  const { serverId, actorName, isAdmin, loaded } = useSession();

  const [players, setPlayers] = useState<Player[]>([]);
  const playerTable = usePlayerTable(players);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [tab, setTab] = useState<Tab>("manual");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // 수동 입력
  const [nickname, setNickname] = useState("");
  const [tier, setTier] = useState<Tier>("GOLD");
  const [division, setDivision] = useState<Division>("IV");
  const [lp, setLp] = useState(0);
  const [mainRole, setMainRole] = useState<Position>("TOP");
  const [subRole, setSubRole] = useState<Position | "">("");

  // Riot ID 조회
  const [riotNickname, setRiotNickname] = useState("");
  const [gameName, setGameName] = useState("");
  const [tagLine, setTagLine] = useState("");
  const [probePuuid, setProbePuuid] = useState<string | null>(null);
  const [probeCurrent, setProbeCurrent] = useState<TierSnapshot | null>(null);
  const [recommendation, setRecommendation] = useState<RoleRecommendation | null>(null);
  const [riotMainRole, setRiotMainRole] = useState<Position>("MID");
  const [seedTier, setSeedTier] = useState<Tier>("GOLD");

  // 일괄 등록
  // error: why the last attempt failed - failed rows stay for a retry.
  const [bulkRows, setBulkRows] = useState<(OCRRiotIdRow & { error?: string })[]>([]);
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);
  const [bulkSummary, setBulkSummary] = useState<string | null>(null);
  const stopBulkRef = useRef(false);

  // 수정 / 삭제
  const [editTarget, setEditTarget] = useState<Player | null>(null);
  const [editDraft, setEditDraft] = useState<Player | null>(null);
  const [editSeedTier, setEditSeedTier] = useState<Tier>("GOLD");

  // Riot 일괄 새로고침
  const [refreshSelection, setRefreshSelection] = useState<Set<number>>(new Set());
  const [refreshProgress, setRefreshProgress] = useState<{ done: number; total: number } | null>(null);
  const [refreshResults, setRefreshResults] = useState<{ nickname: string; ok: boolean; message: string }[]>([]);
  const [refreshStopped, setRefreshStopped] = useState(false);
  const stopRefreshRef = useRef(false);

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
      await api.createPlayer(serverId, {
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
        await api.deactivatePlayer(serverId, player.id);
      } else {
        await api.reactivatePlayer(serverId, player.id);
      }
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleProbe() {
    if (!serverId || !riotNickname || !gameName || !tagLine) return;
    setBusy(true);
    setError(null);
    try {
      const { puuid, current } = await api.probeCurrentSeason(serverId, gameName, tagLine);
      setProbePuuid(puuid);
      setProbeCurrent(current);
      const rec = await inferPositionOrNull(serverId, puuid);
      setRecommendation(rec);
      setRiotMainRole(rec?.main ?? "MID");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleRiotRegister() {
    if (!serverId || !actorName || !probePuuid) return;
    setBusy(true);
    setError(null);
    try {
      await api.registerPlayer(serverId, {
        nickname: riotNickname,
        puuid: probePuuid,
        main_role: riotMainRole,
        current: probeCurrent,
        seed_tier: probeCurrent ? null : seedTier,
        recommendation,
        game_name: gameName,
        tag_line: tagLine,
      });
      setProbePuuid(null);
      setProbeCurrent(null);
      setRecommendation(null);
      setRiotNickname("");
      setGameName("");
      setTagLine("");
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkFile(file: File) {
    if (!serverId) return;
    setBusy(true);
    setError(null);
    try {
      const ext = file.name.split(".").pop()?.toLowerCase();
      const rows =
        ext === "png" || ext === "jpg" || ext === "jpeg"
          ? await api.extractRiotIds(file)
          : await api.parseRosterFile(serverId, file);
      setBulkRows(rows);
      setBulkSummary(null);
      if (rows.length === 0) setInfo("파일에서 라이엇 아이디를 찾지 못했습니다.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkRegister() {
    if (!serverId || !actorName) return;
    const rows = bulkRows;
    if (rows.length === 0) return;
    setBusy(true);
    setError(null);
    setBulkSummary(null);
    stopBulkRef.current = false;
    const added: string[] = [];
    const remaining: (OCRRiotIdRow & { error?: string })[] = [];
    let stopped = false;
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (stopBulkRef.current) {
        stopped = true;
        remaining.push(...rows.slice(i).map((r) => ({ ...r, error: undefined })));
        break;
      }
      setBulkProgress({ done: i, total: rows.length });
      try {
        const { puuid, current } = await api.probeCurrentSeason(serverId, row.game_name, row.tag_line);
        const rec = await inferPositionOrNull(serverId, puuid);
        await api.registerPlayer(serverId, {
          nickname: row.nickname,
          puuid,
          main_role: rec?.main ?? "MID",
          current,
          seed_tier: current ? null : "GOLD",
          recommendation: rec,
          game_name: row.game_name,
          tag_line: row.tag_line,
        });
        added.push(row.nickname);
      } catch (e) {
        remaining.push({ ...row, error: e instanceof ApiError ? e.message : String(e) });
      }
      // Live view: registered rows drop off, failures show their reason.
      setBulkRows([...remaining, ...rows.slice(i + 1)]);
    }
    const failedCount = remaining.filter((r) => r.error).length;
    setBulkSummary(
      `${added.length}명 등록 완료` +
        (failedCount ? `, ${failedCount}명 실패 (아래에서 고쳐서 다시 시도할 수 있습니다)` : "") +
        (stopped ? ` · 중지됨: ${remaining.length - failedCount}명 남음` : "")
    );
    setBulkRows(remaining);
    setBulkProgress(null);
    setBusy(false);
    refresh();
  }

  function startEdit(player: Player) {
    setEditTarget(player);
    setEditDraft({ ...player });
  }

  async function handleSaveEdit() {
    if (!serverId || !actorName || !editDraft || !editTarget) return;
    setBusy(true);
    setError(null);
    try {
      // Seed Rating changes always go through setSeedRating() so they're
      // audited - and its result (not the stale editDraft snapshot, which
      // still carries whatever seed_rating was set before this edit) must
      // be the base for the follow-up field save below, or that save
      // would silently clobber the seed_rating this just set.
      let base = editDraft;
      if (editDraft.tier === "UNRANKED") {
        const afterSeed = await api.setSeedRating(serverId, editTarget.id, editSeedTier, "III");
        base = {
          ...afterSeed,
          division: editDraft.division,
          lp: editDraft.lp,
          main_role: editDraft.main_role,
          sub_role: editDraft.sub_role,
        };
      }
      await api.updatePlayer(serverId, base);
      if (editDraft.internal_rating !== editTarget.internal_rating) {
        await api.overrideInternalRating(serverId, editTarget.id, editDraft.internal_rating);
      }
      setEditTarget(null);
      setEditDraft(null);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  // One request per player, sequentially: each stays far under Vercel's
  // 30s limit, Riot's dev-key rate limit isn't burst, and progress shows
  // as it goes.
  async function handleBulkRefresh() {
    if (!serverId || !actorName) return;
    const targets = players.filter((p) => p.puuid && refreshSelection.has(p.id));
    if (targets.length === 0) return;
    setBusy(true);
    setError(null);
    setRefreshResults([]);
    setRefreshStopped(false);
    stopRefreshRef.current = false;
    const results: { nickname: string; ok: boolean; message: string }[] = [];
    const failed = new Set<number>();
    for (const p of targets) {
      if (stopRefreshRef.current) {
        setRefreshStopped(true);
        break;
      }
      setRefreshProgress({ done: results.length, total: targets.length });
      try {
        const { message } = await api.refreshPlayerFromRiot(serverId, p.id);
        results.push({ nickname: p.nickname, ok: true, message });
      } catch (e) {
        failed.add(p.id);
        results.push({ nickname: p.nickname, ok: false, message: e instanceof ApiError ? e.message : String(e) });
      }
      setRefreshResults([...results]);
    }
    // Leave failures (and anyone not reached before 중지) checked, so a
    // retry is one click.
    const attempted = new Set(targets.slice(0, results.length).map((p) => p.id));
    setRefreshSelection((prev) => new Set([...prev].filter((id) => !attempted.has(id) || failed.has(id))));
    setRefreshProgress(null);
    setBusy(false);
    refresh();
  }

  const riotRows = playerTable.rows.filter((p) => p.puuid);
  const allRiotRowsSelected = riotRows.length > 0 && riotRows.every((p) => refreshSelection.has(p.id));
  const someRiotRowsSelected = riotRows.some((p) => refreshSelection.has(p.id));
  const selectedRefreshCount = players.filter((p) => p.puuid && refreshSelection.has(p.id)).length;

  function toggleAllRiotRows() {
    setRefreshSelection((prev) => {
      const next = new Set(prev);
      for (const p of riotRows) {
        if (allRiotRowsSelected) next.delete(p.id);
        else next.add(p.id);
      }
      return next;
    });
  }

  function toggleRefreshSelection(playerId: number) {
    setRefreshSelection((prev) => {
      const next = new Set(prev);
      if (next.has(playerId)) next.delete(playerId);
      else next.add(playerId);
      return next;
    });
  }

  if (!loaded || !serverId || !actorName) return null;

  return (
    <div>
      <h1>참가자 관리</h1>
      <p className="muted">
        서버 #{serverId} · {actorName}
      </p>
      {error && <p className="error">{error}</p>}
      {info && <p className="muted">{info}</p>}

      {isAdmin && (
      <div className="card">
        <div className="row">
          <button className={tab === "manual" ? "" : "secondary"} onClick={() => setTab("manual")}>
            수동 입력
          </button>
          <button className={tab === "riot" ? "" : "secondary"} onClick={() => setTab("riot")}>
            Riot ID로 자동 조회
          </button>
          <button className={tab === "bulk" ? "" : "secondary"} onClick={() => setTab("bulk")}>
            스크린샷/파일로 일괄 등록
          </button>
        </div>

        {tab === "manual" && (
          <div className="row" style={{ marginTop: 12 }}>
            <input placeholder="닉네임" value={nickname} onChange={(e) => setNickname(e.target.value)} />
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
        )}

        {tab === "riot" && (
          <div style={{ marginTop: 12 }}>
            <div className="row">
              <input
                placeholder="내전에서 쓸 닉네임"
                value={riotNickname}
                onChange={(e) => setRiotNickname(e.target.value)}
              />
              <input placeholder="게임 이름" value={gameName} onChange={(e) => setGameName(e.target.value)} />
              <input placeholder="태그 (# 제외)" value={tagLine} onChange={(e) => setTagLine(e.target.value)} />
              <button onClick={handleProbe} disabled={busy || !riotNickname || !gameName || !tagLine}>
                조회
              </button>
            </div>

            {probePuuid && (
              <div style={{ marginTop: 12 }}>
                {recommendation ? (
                  <p className="muted">
                    Riot 추천 - 주: <strong>{recommendation.main}</strong> (비율{" "}
                    {(recommendation.main_ratio * 100).toFixed(0)}%, 표본 {recommendation.sample_size}판)
                  </p>
                ) : (
                  <p className="muted">
                    포지션을 자동 분석하지 못했습니다 (랭크 게임 이력 없음 또는 조회 지연) - 아래에서 직접 선택해주세요.
                  </p>
                )}
                <div className="row">
                  <select value={riotMainRole} onChange={(e) => setRiotMainRole(e.target.value as Position)}>
                    {POSITIONS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                  {probeCurrent ? (
                    <span className="badge">
                      현재 시즌: {probeCurrent.tier} {probeCurrent.division} {probeCurrent.lp}LP
                    </span>
                  ) : (
                    <>
                      <span className="muted">현재 시즌 언랭 - Seed Tier 지정 필요</span>
                      <select value={seedTier} onChange={(e) => setSeedTier(e.target.value as Tier)}>
                        {RANKED_TIERS.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                    </>
                  )}
                  <button onClick={handleRiotRegister} disabled={busy}>
                    참가자 추가
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "bulk" && (
          <div style={{ marginTop: 12 }}>
            <p className="muted">
              닉네임과 라이엇 아이디(태그 포함)가 함께 보이는 참가자 명단 스크린샷, 또는 CSV/TXT/엑셀 파일을
              업로드하세요.
            </p>
            <input
              type="file"
              accept="image/png,image/jpeg,.csv,.txt,.xlsx,.xls"
              onChange={(e) => e.target.files?.[0] && handleBulkFile(e.target.files[0])}
              disabled={busy}
            />
            {bulkRows.length > 0 && (
              <>
                <div className="table-scroll">
                <table style={{ marginTop: 12 }}>
                  <thead>
                    <tr>
                      <th>닉네임</th>
                      <th>게임 이름</th>
                      <th>태그</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {bulkRows.map((row, i) => (
                      <tr key={i}>
                        {(["nickname", "game_name", "tag_line"] as const).map((field) => (
                          <td key={field}>
                            <input
                              value={row[field]}
                              // OCR misreads are common - every field is
                              // editable, and an empty one is flagged.
                              style={row[field].trim() ? undefined : { borderColor: "#e5484d" }}
                              onChange={(e) => {
                                const next = [...bulkRows];
                                next[i] = { ...row, [field]: e.target.value, error: undefined };
                                setBulkRows(next);
                              }}
                              disabled={busy}
                            />
                            {field === "nickname" && row.error && (
                              <div className="error" style={{ fontSize: 13, marginTop: 4 }}>
                                {row.error}
                              </div>
                            )}
                          </td>
                        ))}
                        <td>
                          <button
                            className="secondary"
                            onClick={() => setBulkRows(bulkRows.filter((_, j) => j !== i))}
                            disabled={busy}
                          >
                            삭제
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
                <p className="muted">
                  OCR 결과는 원본과 꼭 대조해주세요 - 빨간 칸은 읽지 못한 값입니다. 언랭 참가자는 Seed Tier GOLD로
                  임시 등록됩니다 - 등록 후 목록에서 직접 수정해주세요.
                </p>
                <div className="row">
                  <button onClick={handleBulkRegister} disabled={busy}>
                    {bulkRows.some((r) => r.error) ? "다시 시도" : "일괄 조회 및 추가"} ({bulkRows.length}명)
                  </button>
                  {bulkProgress && (
                    <>
                      <span className="muted">
                        등록 중 {bulkProgress.done + 1} / {bulkProgress.total}
                      </span>
                      <button className="secondary" onClick={() => (stopBulkRef.current = true)}>
                        중지
                      </button>
                    </>
                  )}
                </div>
              </>
            )}
            {bulkSummary && !bulkProgress && <p style={{ marginTop: 8 }}>{bulkSummary}</p>}
          </div>
        )}
      </div>
      )}

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h3 style={{ margin: 0 }}>
            참가자 목록 ({playerTable.query ? `${playerTable.rows.length} / ${players.length}` : players.length})
          </h3>
          <div className="row">
            {playerTable.searchInput}
            <label className="row" style={{ gap: 4 }}>
              <input
                type="checkbox"
                checked={includeInactive}
                onChange={(e) => setIncludeInactive(e.target.checked)}
              />
              비활성 포함
            </label>
          </div>
        </div>
        {isAdmin && players.some((p) => p.puuid) && (
          <div className="row" style={{ marginTop: 8 }}>
            <button onClick={handleBulkRefresh} disabled={busy || selectedRefreshCount === 0}>
              Riot 정보 새로고침 ({selectedRefreshCount}명)
            </button>
            {refreshProgress ? (
              <>
                <span className="muted">
                  새로고침 중 {refreshProgress.done + 1} / {refreshProgress.total}
                </span>
                <button className="secondary" onClick={() => (stopRefreshRef.current = true)}>
                  중지
                </button>
              </>
            ) : (
              <span className="muted">왼쪽 체크박스로 Riot 연동 참가자를 고르세요</span>
            )}
          </div>
        )}
        {refreshResults.length > 0 && !refreshProgress && (
          <div style={{ marginTop: 8 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong>
                새로고침 결과: 성공 {refreshResults.filter((r) => r.ok).length}명, 실패{" "}
                {refreshResults.filter((r) => !r.ok).length}명{refreshStopped ? " (중지됨)" : ""}
              </strong>
              <button className="secondary" onClick={() => setRefreshResults([])}>
                닫기
              </button>
            </div>
            <ul style={{ margin: "6px 0 0", paddingLeft: 18, maxHeight: 200, overflowY: "auto" }}>
              {refreshResults.map((r, i) => (
                <li key={i} className={r.ok ? "muted" : "error"}>
                  {r.ok ? r.message : `${r.nickname}: ${r.message}`}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {isAdmin && (
              <th>
                {riotRows.length > 0 && (
                  <input
                    type="checkbox"
                    aria-label="Riot 연동 참가자 전체 선택"
                    checked={allRiotRowsSelected}
                    ref={(el) => {
                      if (el) el.indeterminate = someRiotRowsSelected && !allRiotRowsSelected;
                    }}
                    onChange={toggleAllRiotRows}
                    disabled={busy}
                  />
                )}
              </th>
              )}
              {playerTable.sortTh("nickname", "닉네임")}
              {playerTable.sortTh("tier", "티어")}
              {playerTable.sortTh("position", "포지션")}
              {playerTable.sortTh("rating", "Final Rating")}
              {playerTable.sortTh("source", "출처")}
              {playerTable.sortTh("status", "상태")}
              {isAdmin && <th></th>}
            </tr>
          </thead>
          <tbody>
            {playerTable.rows.map((p) => (
              <tr key={p.id} style={{ opacity: p.is_active ? 1 : 0.5 }}>
                {isAdmin && (
                <td>
                  {p.puuid && (
                    <input
                      type="checkbox"
                      aria-label={`${p.nickname} 선택`}
                      checked={refreshSelection.has(p.id)}
                      onChange={() => toggleRefreshSelection(p.id)}
                      disabled={busy}
                    />
                  )}
                </td>
                )}
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
                {isAdmin && (
                <td>
                  <div className="row">
                    <button className="secondary" onClick={() => startEdit(p)} disabled={busy}>
                      수정
                    </button>
                    <button className="secondary" onClick={() => handleToggleActive(p)} disabled={busy}>
                      {p.is_active ? "비활성화" : "재활성화"}
                    </button>
                  </div>
                </td>
                )}
              </tr>
            ))}
            {playerTable.rows.length === 0 && (
              <tr>
                <td colSpan={isAdmin ? 8 : 6} className="muted">
                  {players.length === 0 ? "등록된 참가자가 없습니다." : "검색 결과가 없습니다."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      {editDraft && (
        <div className="card">
          <h3>참가자 수정 - {editDraft.nickname}</h3>
          <div className="row" style={{ flexWrap: "wrap", gap: 12 }}>
            <select
              value={editDraft.tier}
              onChange={(e) => setEditDraft({ ...editDraft, tier: e.target.value as Tier })}
            >
              {TIERS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              value={editDraft.division}
              onChange={(e) => setEditDraft({ ...editDraft, division: e.target.value as Division })}
            >
              {DIVISIONS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
            <input
              type="number"
              value={editDraft.lp}
              onChange={(e) => setEditDraft({ ...editDraft, lp: Number(e.target.value) })}
              style={{ width: 80 }}
            />
            <select
              value={editDraft.main_role}
              onChange={(e) => setEditDraft({ ...editDraft, main_role: e.target.value as Position })}
            >
              {POSITIONS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <select
              value={editDraft.sub_role ?? ""}
              onChange={(e) =>
                setEditDraft({ ...editDraft, sub_role: (e.target.value || null) as Position | null })
              }
            >
              <option value="">부 포지션 없음</option>
              {POSITIONS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          {editDraft.tier === "UNRANKED" && (
            <div className="row" style={{ marginTop: 8 }}>
              <span className="muted">Seed Rating 티어 (운영자 판단)</span>
              <select value={editSeedTier} onChange={(e) => setEditSeedTier(e.target.value as Tier)}>
                {RANKED_TIERS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="row" style={{ marginTop: 12 }}>
            <label className="muted">Internal Rating 직접 수정</label>
            <input
              type="number"
              value={editDraft.internal_rating}
              onChange={(e) => setEditDraft({ ...editDraft, internal_rating: Number(e.target.value) })}
              style={{ width: 100 }}
            />
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={handleSaveEdit} disabled={busy}>
              수정 저장
            </button>
            <button className="secondary" onClick={() => setEditDraft(null)} disabled={busy}>
              취소
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
