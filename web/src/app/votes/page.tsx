"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, Match, Player } from "@/lib/api";
import { useSession } from "@/lib/session";
import { formatUtc } from "@/lib/time";

export default function VotesPage() {
  const router = useRouter();
  const { serverId, actorName, isAdmin, loaded } = useSession();

  const [pending, setPending] = useState<Match[]>([]);
  const [players, setPlayers] = useState<Player[]>([]);
  // undefined = still loading; null = this login isn't linked to a player.
  const [me, setMe] = useState<Player | null | undefined>(undefined);
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
    api.myPlayer(serverId).then(setMe).catch(() => setMe(null));
  }, [serverId]);

  useEffect(() => {
    if (loaded && (!serverId || !actorName)) {
      router.push("/");
      return;
    }
    refresh();
  }, [loaded, serverId, actorName, router, refresh]);

  const playersById = useMemo(() => new Map(players.map((p) => [p.id, p])), [players]);
  const nameOf = (id: number | null | undefined) => (id != null ? playersById.get(id)?.nickname ?? `#${id}` : "?");
  const selectedMatch = pending.find((m) => m.id === selectedMatchId) ?? null;
  const candidates = selectedMatch
    ? selectedMatch.participants.map((p) => playersById.get(p.player_id)).filter((p): p is Player => !!p)
    : [];
  const meInMatch = !!me && candidates.some((c) => c.id === me.id);

  // Default voter: yourself when you played in this match.
  useEffect(() => {
    setVotedId("");
    setVoterId(me && selectedMatch?.participants.some((p) => p.player_id === me.id) ? me.id : "");
  }, [selectedMatchId, me, selectedMatch]);

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

  const effectiveVoter = isAdmin ? (voterId === "" ? null : voterId) : meInMatch && me ? me.id : null;
  const onBehalf = isAdmin && effectiveVoter !== null && effectiveVoter !== me?.id;

  async function handleVote() {
    if (!serverId || !selectedMatchId || effectiveVoter === null || votedId === "") return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await api.castVote(serverId, selectedMatchId, Number(votedId), onBehalf ? effectiveVoter : undefined);
      setInfo(
        onBehalf
          ? `${nameOf(effectiveVoter)}의 표로 ${nameOf(Number(votedId))}에게 투표했습니다.`
          : `${nameOf(Number(votedId))}에게 투표했습니다.`
      );
      setVotedId("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirmMvp() {
    if (!serverId || !selectedMatchId || tally === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.setUserMvp(serverId, selectedMatchId, tally);
      setInfo(`User MVP를 ${nameOf(tally)}(으)로 확정했습니다.`);
      setSelectedMatchId(null);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!loaded || !serverId || !actorName) return null;

  const blockedReason =
    isAdmin || !selectedMatch || me === undefined
      ? null
      : me === null
        ? `로그인 이름(${actorName})과 같은 닉네임의 참가자가 없어 투표할 수 없습니다. 관리자에게 '서버 관리'에서 참가자 연결을 요청해주세요.`
        : !meInMatch
          ? "이 경기에 참가한 사람만 투표할 수 있습니다."
          : null;

  return (
    <div>
      <h1>User MVP 투표</h1>
      {error && <p className="error">{error}</p>}
      {info && <p className="muted">{info}</p>}
      {me && <p className="muted">{me.nickname}(으)로 투표합니다.</p>}

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
                  #{m.id} ({formatUtc(m.played_at)}) - AI MVP: {nameOf(m.ai_mvp_player_id)}
                </option>
              ))}
            </select>
          </div>

          {selectedMatch && blockedReason && <p className="muted" style={{ marginTop: 12 }}>{blockedReason}</p>}

          {selectedMatch && !blockedReason && candidates.length > 0 && (
            <div className="row" style={{ marginTop: 12 }}>
              {isAdmin && (
                <select
                  aria-label="투표자"
                  value={voterId}
                  onChange={(e) => setVoterId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">투표자 선택</option>
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.id === me?.id ? `${c.nickname} (나)` : `${c.nickname} (대리 투표)`}
                    </option>
                  ))}
                </select>
              )}
              <select
                aria-label="MVP로 투표할 선수"
                value={votedId}
                onChange={(e) => setVotedId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">MVP로 투표할 선수</option>
                {candidates
                  .filter((c) => c.id !== effectiveVoter)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nickname}
                    </option>
                  ))}
              </select>
              <button onClick={handleVote} disabled={busy || effectiveVoter === null || votedId === ""}>
                투표하기
              </button>
            </div>
          )}

          {selectedMatch && (
            <div style={{ marginTop: 16 }}>
              <h3>현재 집계</h3>
              {tally === null ? (
                <p className="muted">아직 투표가 없습니다.</p>
              ) : (
                <>
                  <p>
                    현재 1위: <strong>{nameOf(tally)}</strong>
                  </p>
                  {isAdmin && (
                    <button onClick={handleConfirmMvp} disabled={busy}>
                      투표 마감 및 User MVP 확정
                    </button>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
