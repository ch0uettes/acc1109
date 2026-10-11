"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, DecisionLogEntry, Player } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function StatsPage() {
  const router = useRouter();
  const { serverId, actorName, loaded } = useSession();

  const [leaderboard, setLeaderboard] = useState<Player[]>([]);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [decisions, setDecisions] = useState<DecisionLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loaded && (!serverId || !actorName)) {
      router.push("/");
      return;
    }
    if (!serverId) return;
    api.leaderboard(serverId).then(setLeaderboard).catch((e) => setError(String(e)));
    api.aiMvpAccuracy(serverId).then(setAccuracy).catch(() => undefined);
    api.recentDecisions(serverId, 20).then(setDecisions).catch(() => undefined);
  }, [loaded, serverId, actorName, router]);

  if (!loaded || !serverId || !actorName) return null;

  return (
    <div>
      <h1>통계</h1>
      {error && <p className="error">{error}</p>}

      <div className="card">
        <h3>리더보드</h3>
        {leaderboard.length === 0 ? (
          <p className="muted">데이터가 없습니다.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>닉네임</th>
                <th>Final Rating</th>
                <th>게임 수</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((p) => (
                <tr key={p.id}>
                  <td>{p.nickname}</td>
                  <td>{(p.official_rating ?? p.seed_rating ?? 0).toFixed(1)}</td>
                  <td>{p.games_played}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

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
                  <td>{new Date(d.created_at).toLocaleString()}</td>
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
        )}
      </div>
    </div>
  );
}
