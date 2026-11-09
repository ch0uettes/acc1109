"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, DecisionLogEntry, PlayerRecord, PlayerRecordDetail } from "@/lib/api";
import { POSITION_ORDER } from "@/lib/playerTable";
import { useSession } from "@/lib/session";
import { formatUtc } from "@/lib/time";
import RatingChart, { RatingPoint } from "./RatingChart";

function winRate(r: { games: number; wins: number }): string {
  return r.games ? `${Math.round((r.wins / r.games) * 100)}%` : "-";
}

function signed(n: number): string {
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}`;
}

export default function StatsPage() {
  const router = useRouter();
  const { serverId, actorName, loaded } = useSession();

  const [records, setRecords] = useState<PlayerRecord[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<PlayerRecordDetail | null>(null);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [decisions, setDecisions] = useState<DecisionLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loaded && (!serverId || !actorName)) {
      router.push("/");
      return;
    }
    if (!serverId) return;
    api.playerRecords(serverId).then(setRecords).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    // Open your own record first when this login is linked to a player.
    api
      .myPlayer(serverId)
      .then((me) => me && setSelectedId((cur) => cur ?? me.id))
      .catch(() => undefined);
    api.aiMvpAccuracy(serverId).then(setAccuracy).catch(() => undefined);
    api.recentDecisions(serverId, 20).then(setDecisions).catch(() => undefined);
  }, [loaded, serverId, actorName, router]);

  useEffect(() => {
    if (!serverId || selectedId === null) {
      setDetail(null);
      return;
    }
    api
      .playerRecord(serverId, selectedId)
      .then(setDetail)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [serverId, selectedId]);

  const chartPoints: RatingPoint[] = useMemo(() => {
    const h = detail?.rating_history ?? [];
    if (h.length === 0) return [];
    return [
      { label: "시작", played_at: null, rating: h[0].rating_after - h[0].delta, delta: null, won: null },
      ...h.map((p) => ({
        label: `경기 #${p.match_id}`,
        played_at: p.played_at,
        rating: p.rating_after,
        delta: p.delta,
        won: p.won,
      })),
    ];
  }, [detail]);

  function select(id: number) {
    setSelectedId(id);
    // On phones the detail card sits below a long table - bring it into view.
    requestAnimationFrame(() => document.getElementById("player-record")?.scrollIntoView({ behavior: "smooth" }));
  }

  if (!loaded || !serverId || !actorName) return null;

  return (
    <div>
      <h1>통계</h1>
      {error && <p className="error">{error}</p>}

      <div className="card">
        <h3>리더보드</h3>
        <p className="muted">이름을 누르면 아래에 전적이 나옵니다.</p>
        {records.length === 0 ? (
          <p className="muted">데이터가 없습니다.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>닉네임</th>
                  <th>레이팅</th>
                  <th>전적</th>
                  <th>승률</th>
                  <th>MVP (AI / 투표)</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => (
                  <tr key={r.player_id} className={r.player_id === selectedId ? "row-selected" : undefined}>
                    <td>{i + 1}</td>
                    <td>
                      <button type="button" className="link-button" onClick={() => select(r.player_id)}>
                        {r.nickname}
                      </button>
                      {!r.is_active && <span className="muted"> (비활성)</span>}
                    </td>
                    <td>{r.final_rating.toFixed(1)}</td>
                    <td>{r.games ? `${r.wins}승 ${r.losses}패` : "-"}</td>
                    <td>{winRate(r)}</td>
                    <td>
                      {r.ai_mvp} / {r.user_mvp}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {detail && (
        <div className="card" id="player-record">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3 style={{ margin: 0 }}>{detail.record.nickname} 전적</h3>
            <button type="button" className="secondary" onClick={() => setSelectedId(null)}>
              닫기
            </button>
          </div>
          <div className="stat-tiles">
            <div>
              <span className="muted">게임</span>
              <strong>{detail.record.games}</strong>
            </div>
            <div>
              <span className="muted">승률</span>
              <strong>{winRate(detail.record)}</strong>
              <span className="muted">
                {detail.record.wins}승 {detail.record.losses}패
              </span>
            </div>
            <div>
              <span className="muted">AI MVP</span>
              <strong>{detail.record.ai_mvp}</strong>
            </div>
            <div>
              <span className="muted">투표 MVP</span>
              <strong>{detail.record.user_mvp}</strong>
            </div>
          </div>

          {detail.record.games === 0 ? (
            <p className="muted">아직 기록된 경기가 없습니다.</p>
          ) : (
            <>
              <h4>포지션별</h4>
              <div className="row" style={{ gap: 16 }}>
                {[...detail.positions]
                  .sort((a, b) => POSITION_ORDER.indexOf(a.position) - POSITION_ORDER.indexOf(b.position))
                  .map((p) => (
                    <span key={p.position}>
                      {p.position} <span className="muted">{p.games}판 {winRate(p)}</span>
                    </span>
                  ))}
              </div>

              <h4>내부 레이팅 변화</h4>
              <p className="muted" style={{ marginTop: -8 }}>
                경기 결과로만 움직이는 점수입니다. 리더보드의 레이팅은 이 점수와 티어 점수를 합친 값입니다.
              </p>
              {chartPoints.length >= 2 ? (
                <RatingChart points={chartPoints} />
              ) : (
                <p className="muted">
                  레이팅 변화는 경기별 변화량을 저장하기 시작한 뒤의 경기부터 보입니다.
                </p>
              )}

              <h4>최근 경기</h4>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>경기</th>
                      <th>결과</th>
                      <th>포지션</th>
                      <th>레이팅 변화</th>
                      <th>MVP</th>
                      <th>같은 팀</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.recent.map((m) => (
                      <tr key={m.match_id}>
                        <td>
                          #{m.match_id} <span className="muted">{formatUtc(m.played_at)}</span>
                        </td>
                        <td>{m.won ? "승" : "패"}</td>
                        <td>{m.position}</td>
                        <td>{m.delta === null ? <span className="muted">-</span> : signed(m.delta)}</td>
                        <td>{[m.ai_mvp && "AI", m.user_mvp && "투표"].filter(Boolean).join(", ") || ""}</td>
                        <td>{m.teammates.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {accuracy !== null && (
        <div className="card">
          <h3>AI MVP 적중률</h3>
          <p style={{ fontSize: 28, fontWeight: 700 }}>{(accuracy * 100).toFixed(1)}%</p>
        </div>
      )}

      <div className="card">
        <h3>최근 팀 생성 기록 (AI Decision Log)</h3>
        <p className="muted">
          AI가 추천한 조합과 실제로 운영자가 선택한 조합을 비교합니다 - &apos;선택된 순위&apos;가
          1위가 아니면 AI 추천을 사람이 뒤집은 경우입니다.
        </p>
        {decisions.length === 0 ? (
          <p className="muted">아직 저장된 팀 생성 기록이 없습니다.</p>
        ) : (
          <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>시각</th>
                <th>전략</th>
                <th>참가자 수</th>
                <th>실행 시간(초)</th>
                <th>선택된 순위</th>
                <th>사유</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((d) => (
                <tr key={d.id ?? d.created_at}>
                  <td>{formatUtc(d.created_at)}</td>
                  <td>{d.strategy_name}</td>
                  <td>{d.player_ids.length}</td>
                  <td>{d.execution_time_seconds?.toFixed(3) ?? "-"}</td>
                  <td>
                    {d.chosen_rank}위{d.chosen_rank !== 1 ? " (AI 1위 아님)" : ""}
                  </td>
                  <td>{d.reason ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}
