"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, MatchResultData, OCRPlayerRow, Player, Team } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function MatchesPage() {
  const router = useRouter();
  const { serverId, actorName, loaded } = useSession();

  const [teams, setTeams] = useState<Team[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [detailFile, setDetailFile] = useState<File | null>(null);
  const [ocrResult, setOcrResult] = useState<MatchResultData | null>(null);
  const [winnerIndex, setWinnerIndex] = useState<number>(0);
  const [note, setNote] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (loaded && (!serverId || !actorName)) {
      router.push("/");
      return;
    }
    const raw = window.localStorage.getItem("balancer.lastTeams");
    if (raw) {
      try {
        setTeams(JSON.parse(raw));
      } catch {
        setTeams(null);
      }
    }
  }, [loaded, serverId, actorName, router]);

  const allPlayers = useMemo(() => {
    const map = new Map<string, Player>();
    (teams ?? []).forEach((team) => team.players.forEach((p) => map.set(p.nickname, p)));
    return map;
  }, [teams]);

  async function handleAnalyze() {
    if (!serverId || !file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.extractMatchResult(serverId, file, Array.from(allPlayers.keys()));
      setOcrResult(result);
      if (result.winning_team_index !== null) setWinnerIndex(result.winning_team_index);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
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
      setError(e instanceof ApiError ? e.message : String(e));
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

  async function handleRecord() {
    if (!serverId || !actorName || !teams) return;
    setBusy(true);
    setError(null);
    try {
      const statsByPlayerId: Record<number, OCRPlayerRow> = {};
      if (ocrResult) {
        for (const row of ocrResult.participants) {
          const player = allPlayers.get(row.raw_name);
          if (player) statsByPlayerId[player.id] = row;
        }
      }
      const match = await api.recordMatch(serverId, actorName, {
        teams,
        winning_team_index: winnerIndex,
        note: note || null,
        match_stats_by_player_id: Object.fromEntries(
          Object.entries(statsByPlayerId).map(([id, row]) => [
            id,
            {
              kills: row.kills,
              deaths: row.deaths,
              assists: row.assists,
              cs: row.cs,
              gold: row.gold,
              damage: row.damage,
              vision_score: row.vision_score,
            },
          ])
        ),
      });
      setInfo(`경기 저장 완료 (AI MVP: player_id=${match.ai_mvp_player_id})`);
      setSaved(true);
      window.localStorage.removeItem("balancer.lastTeams");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!loaded || !serverId || !actorName) return null;

  if (!teams || saved) {
    return (
      <div>
        <h1>경기 저장</h1>
        {info && <p className="muted">{info}</p>}
        <p className="muted">먼저 &apos;팀 생성&apos; 메뉴에서 팀을 만들고 저장해주세요.</p>
      </div>
    );
  }

  return (
    <div>
      <h1>경기 저장</h1>
      {error && <p className="error">{error}</p>}
      {info && <p className="muted">{info}</p>}

      <div className="card">
        <h3>현재 팀</h3>
        <div className="row" style={{ alignItems: "flex-start" }}>
          {teams.map((team) => (
            <div key={team.index} style={{ minWidth: 160 }}>
              <strong>{team.index + 1}팀</strong>
              {team.players.map((p) => (
                <div key={p.id} className="muted">
                  {p.nickname}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>결과창 스크린샷으로 자동 분석 (선택)</h3>
        <div className="row">
          <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button onClick={handleAnalyze} disabled={busy || !file}>
            스크린샷 분석
          </button>
        </div>

        {ocrResult && (
          <>
            <table style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th>이름</th>
                  <th>팀</th>
                  <th>K</th>
                  <th>D</th>
                  <th>A</th>
                  <th>CS</th>
                  <th>골드</th>
                  <th>딜량</th>
                  <th>시야</th>
                </tr>
              </thead>
              <tbody>
                {ocrResult.participants.map((p, i) => (
                  <tr key={i}>
                    <td>
                      <input
                        value={p.raw_name}
                        onChange={(e) => updateRow(i, { raw_name: e.target.value })}
                        style={{ width: 100 }}
                      />
                    </td>
                    <td>{p.team_index + 1}팀</td>
                    {(["kills", "deaths", "assists", "cs", "gold", "damage", "vision_score"] as const).map(
                      (field) => (
                        <td key={field}>
                          <input
                            type="number"
                            value={p[field]}
                            onChange={(e) => updateRow(i, { [field]: Number(e.target.value) })}
                            style={{ width: 70 }}
                          />
                        </td>
                      )
                    )}
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="row" style={{ marginTop: 8 }}>
              <input type="file" accept="image/*" onChange={(e) => setDetailFile(e.target.files?.[0] ?? null)} />
              <button className="secondary" onClick={handleAnalyzeDetail} disabled={busy || !detailFile}>
                상세 스탯 분석 (선택)
              </button>
            </div>
          </>
        )}
      </div>

      <div className="card">
        <div className="row">
          <label>승리 팀</label>
          <select value={winnerIndex} onChange={(e) => setWinnerIndex(Number(e.target.value))}>
            {teams.map((team) => (
              <option key={team.index} value={team.index}>
                {team.index + 1}팀
              </option>
            ))}
          </select>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <input placeholder="비고" value={note} onChange={(e) => setNote(e.target.value)} style={{ flex: 1 }} />
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={handleRecord} disabled={busy}>
            경기 결과 저장
          </button>
        </div>
      </div>
    </div>
  );
}
