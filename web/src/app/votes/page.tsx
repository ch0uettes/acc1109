"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, Match, Player } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function VotesPage() {
  const router = useRouter();
  const { serverId, actorName, loaded } = useSession();

  const [pending, setPending] = useState<Match[]>([]);
  const [players, setPlayers] = useState<Player[]>([]);
  const [selectedMatchId, setSelectedMatchId] = useState<number | null>(null);
  const [voterId, setVoterId] = useState<number | "">("");
  const [votedId, setVotedId] = useState<number | "">("");
  const [tally, setTallyState] = useState<number | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    if (!serverId) return;
    api.listPendingVotes(serverId).then(setPending).catch((e) => setError(String(e)));
    api.listPlayers(serverId, true).then(setPlayers).catch(() => undefined);
  }, [serverId]);

  useEffect(() => {
    if (loaded && (!serverId || !actorName)) {
      router.push("/");
      return;
    }
    refresh();
  }, [loaded, serverId, actorName, router, refresh]);

  const playersById = useMemo(() => new Map(players.map((p) => [p.id, p])), [players]);
  const selectedMatch = pending.find((m) => m.id === selectedMatchId) ?? null;
  const candidates = selectedMatch
    ? selectedMatch.participants
        .map((p) => playersById.get(p.player_id))
        .filter((p): p is Player => !!p)
    : [];

  useEffect(() => {
    if (!serverId || !selectedMatchId) {
      setTallyState(null);
      return;
    }
    api
      .tallyVote(serverId, selectedMatchId)
      .then(setTallyState)
      .catch(() => setTallyState(null));
  }, [serverId, selectedMatchId, busy]);

  async function handleVote() {
    if (!serverId || !actorName || !selectedMatchId || !voterId || !votedId) return;
    setBusy(true);
    setError(null);
    try {
      await api.castVote(serverId, actorName, selectedMatchId, Number(voterId), Number(votedId));
      setInfo("투표 완료");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirmMvp() {
    if (!serverId || !actorName || !selectedMatchId || tally === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.setUserMvp(serverId, actorName, selectedMatchId, tally);
      setInfo(`User MVP를 ${playersById.get(tally)?.nickname ?? tally}(으)로 확정했습니다.`);
      setSelectedMatchId(null);
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
      <h1>User MVP 투표</h1>
      {error && <p className="error">{error}</p>}
      {info && <p className="muted">{info}</p>}

      {pending.length === 0 ? (
        <p className="muted">투표 대기 중인 경기가 없습니다.</p>
      ) : (
        <div className="card">
          <div className="row">
            <select
              value={selectedMatchId ?? ""}
              onChange={(e) => setSelectedMatchId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">투표할 경기 선택</option>
              {pending.map((m) => (
                <option key={m.id ?? ""} value={m.id ?? ""}>
                  #{m.id} ({new Date(m.played_at).toLocaleString()}) - AI MVP:{" "}
                  {playersById.get(m.ai_mvp_player_id ?? -1)?.nickname ?? "?"}
                </option>
              ))}
            </select>
          </div>

          {selectedMatch && candidates.length > 0 && (
            <>
              <div className="row" style={{ marginTop: 12 }}>
                <select value={voterId} onChange={(e) => setVoterId(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">투표자</option>
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nickname}
                    </option>
                  ))}
                </select>
                <select value={votedId} onChange={(e) => setVotedId(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">MVP로 투표할 선수</option>
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nickname}
                    </option>
                  ))}
                </select>
                <button onClick={handleVote} disabled={busy || !voterId || !votedId}>
                  투표하기
                </button>
              </div>

              <div style={{ marginTop: 16 }}>
                <h3>현재 집계</h3>
                {tally === null ? (
                  <p className="muted">아직 투표가 없습니다.</p>
                ) : (
                  <>
                    <p>
                      현재 1위: <strong>{playersById.get(tally)?.nickname ?? tally}</strong>
                    </p>
                    <button onClick={handleConfirmMvp} disabled={busy}>
                      투표 마감 및 User MVP 확정
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
