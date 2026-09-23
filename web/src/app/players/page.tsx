"use client";

import { useCallback, useEffect, useState } from "react";
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

export default function PlayersPage() {
  const router = useRouter();
  const { serverId, actorName, loaded } = useSession();

  const [players, setPlayers] = useState<Player[]>([]);
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
  const [bulkRows, setBulkRows] = useState<OCRRiotIdRow[]>([]);

  // 수정 / 삭제
  const [editTarget, setEditTarget] = useState<Player | null>(null);
  const [editDraft, setEditDraft] = useState<Player | null>(null);
  const [editSeedTier, setEditSeedTier] = useState<Tier>("GOLD");

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

  async function handleProbe() {
    if (!serverId || !riotNickname || !gameName || !tagLine) return;
    setBusy(true);
    setError(null);
    try {
      const { puuid, current } = await api.probeCurrentSeason(serverId, gameName, tagLine);
      const rec = await api.inferPositionByPuuid(serverId, puuid);
      setProbePuuid(puuid);
      setProbeCurrent(current);
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
      await api.registerPlayer(serverId, actorName, {
        nickname: riotNickname,
        puuid: probePuuid,
        main_role: riotMainRole,
        current: probeCurrent,
        seed_tier: probeCurrent ? null : seedTier,
        recommendation,
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
      if (rows.length === 0) setInfo("파일에서 라이엇 아이디를 찾지 못했습니다.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkRegister() {
    if (!serverId || !actorName) return;
    setBusy(true);
    setError(null);
    const added: string[] = [];
    const failed: string[] = [];
    try {
      for (const row of bulkRows) {
        try {
          const { puuid, current } = await api.probeCurrentSeason(serverId, row.game_name, row.tag_line);
          const rec = await api.inferPositionByPuuid(serverId, puuid);
          await api.registerPlayer(serverId, actorName, {
            nickname: row.nickname,
            puuid,
            main_role: rec?.main ?? "MID",
            current,
            seed_tier: current ? null : "GOLD",
            recommendation: rec,
          });
          added.push(row.nickname);
        } catch (e) {
          failed.push(`${row.nickname}: ${e instanceof ApiError ? e.message : String(e)}`);
        }
      }
      setInfo(
        `${added.length}명 등록 완료` + (failed.length ? ` / ${failed.length}명 실패: ${failed.join(", ")}` : "")
      );
      setBulkRows([]);
      refresh();
    } finally {
      setBusy(false);
    }
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
        const afterSeed = await api.setSeedRating(serverId, actorName, editTarget.id, editSeedTier, "III");
        base = {
          ...afterSeed,
          division: editDraft.division,
          lp: editDraft.lp,
          main_role: editDraft.main_role,
          sub_role: editDraft.sub_role,
        };
      }
      await api.updatePlayer(serverId, actorName, base);
      if (editDraft.internal_rating !== editTarget.internal_rating) {
        await api.overrideInternalRating(serverId, actorName, editTarget.id, editDraft.internal_rating);
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

  async function handleRefreshFromRiot(playerId: number) {
    if (!serverId || !actorName) return;
    setBusy(true);
    setError(null);
    try {
      await api.refreshPlayerFromRiot(serverId, actorName, playerId);
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
      {info && <p className="muted">{info}</p>}

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
                  <p className="muted">랭크 게임 이력이 없어 포지션을 자동 분석할 수 없습니다.</p>
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
            />
            {bulkRows.length > 0 && (
              <>
                <table style={{ marginTop: 12 }}>
                  <thead>
                    <tr>
                      <th>닉네임</th>
                      <th>게임 이름</th>
                      <th>태그</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bulkRows.map((row, i) => (
                      <tr key={i}>
                        <td>
                          <input
                            value={row.nickname}
                            onChange={(e) => {
                              const next = [...bulkRows];
                              next[i] = { ...row, nickname: e.target.value };
                              setBulkRows(next);
                            }}
                          />
                        </td>
                        <td>{row.game_name}</td>
                        <td>{row.tag_line}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted">
                  언랭 참가자는 Seed Tier GOLD로 임시 등록됩니다 - 등록 후 목록에서 직접 수정해주세요.
                </p>
                <button onClick={handleBulkRegister} disabled={busy}>
                  일괄 조회 및 추가
                </button>
              </>
            )}
          </div>
        )}
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
                  <div className="row">
                    <button className="secondary" onClick={() => startEdit(p)} disabled={busy}>
                      수정
                    </button>
                    {p.puuid && (
                      <button className="secondary" onClick={() => handleRefreshFromRiot(p.id)} disabled={busy}>
                        새로고침
                      </button>
                    )}
                    <button className="secondary" onClick={() => handleToggleActive(p)} disabled={busy}>
                      {p.is_active ? "비활성화" : "재활성화"}
                    </button>
                  </div>
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
