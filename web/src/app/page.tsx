"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, Server, SessionResponse } from "@/lib/api";
import { saveSession, useSession } from "@/lib/session";

export default function ServerPickerPage() {
  const router = useRouter();
  const { serverId, actorName, loaded, clear } = useSession();

  const [servers, setServers] = useState<Server[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [newServerName, setNewServerName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [newJoinCode, setNewJoinCode] = useState("");
  const [ownerPin, setOwnerPin] = useState("");
  const [creationCode, setCreationCode] = useState("");

  const [chosenServerId, setChosenServerId] = useState<number | "">("");
  const [nameInput, setNameInput] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [pin, setPin] = useState("");

  useEffect(() => {
    api
      .listServers()
      .then(setServers)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  async function enter(action: () => Promise<SessionResponse>) {
    setBusy(true);
    setError(null);
    try {
      const { token, member } = await action();
      saveSession(member, token);
      router.push("/players");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function handleCreateServer() {
    if (!newServerName || !ownerName || !newJoinCode || !ownerPin) return;
    enter(() =>
      api.createServer({
        name: newServerName,
        owner_display_name: ownerName,
        join_code: newJoinCode,
        owner_pin: ownerPin,
        creation_code: creationCode || undefined,
      })
    );
  }

  function handleJoin() {
    if (!chosenServerId || !nameInput) return;
    enter(() => api.login(Number(chosenServerId), nameInput, joinCode, pin));
  }

  if (!loaded) return null;

  return (
    <div>
      <h1>AI Inhouse Balancer</h1>
      {serverId && actorName && (
        <p className="muted">
          현재: 서버 #{serverId} · {actorName} — <a href="/players">참가자 관리로 이동</a> ·{" "}
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              clear();
            }}
          >
            나가기
          </a>
        </p>
      )}
      {error && <p className="error">{error}</p>}

      <div className="card">
        <h3>서버 입장</h3>
        <div className="row" style={{ flexWrap: "wrap" }}>
          <select
            value={chosenServerId}
            onChange={(e) => setChosenServerId(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">서버 선택</option>
            {servers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} (#{s.id})
              </option>
            ))}
          </select>
          <input placeholder="내 이름" value={nameInput} onChange={(e) => setNameInput(e.target.value)} />
          <input
            type="password"
            placeholder="입장 코드"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
          />
          <input
            type="password"
            inputMode="numeric"
            placeholder="PIN (관리자만)"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleJoin()}
          />
          <button onClick={handleJoin} disabled={busy || !chosenServerId || !nameInput}>
            입장
          </button>
        </div>
        <p className="muted">
          일반 참가자는 입장 코드만 입력하면 됩니다. Owner/관리자는 PIN도 필요하며, PIN이 아직 없다면 이번에
          입력한 PIN이 새로 설정됩니다.
        </p>
      </div>

      <div className="card">
        <h3>새 서버 만들기</h3>
        <div className="row" style={{ flexWrap: "wrap" }}>
          <input placeholder="새 서버 이름" value={newServerName} onChange={(e) => setNewServerName(e.target.value)} />
          <input
            placeholder="내 이름 (Owner가 됩니다)"
            value={ownerName}
            onChange={(e) => setOwnerName(e.target.value)}
          />
          <input
            type="password"
            placeholder="입장 코드 (4자 이상)"
            value={newJoinCode}
            onChange={(e) => setNewJoinCode(e.target.value)}
          />
          <input
            type="password"
            inputMode="numeric"
            placeholder="내 PIN (4자 이상)"
            value={ownerPin}
            onChange={(e) => setOwnerPin(e.target.value)}
          />
          <input
            type="password"
            placeholder="서버 생성 코드"
            value={creationCode}
            onChange={(e) => setCreationCode(e.target.value)}
          />
          <button
            onClick={handleCreateServer}
            disabled={busy || !newServerName || !ownerName || !newJoinCode || !ownerPin}
          >
            서버 만들기
          </button>
        </div>
      </div>
    </div>
  );
}
