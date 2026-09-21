"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, Server } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function ServerPickerPage() {
  const router = useRouter();
  const { serverId, actorName, loaded, setServerId, setActorName } = useSession();

  const [servers, setServers] = useState<Server[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [newServerName, setNewServerName] = useState("");
  const [ownerName, setOwnerName] = useState("");

  const [chosenServerId, setChosenServerId] = useState<number | "">("");
  const [nameInput, setNameInput] = useState("");

  useEffect(() => {
    api
      .listServers()
      .then(setServers)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  async function handleCreateServer() {
    if (!newServerName || !ownerName) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createServer(newServerName, ownerName);
      setServerId(created.id);
      setActorName(ownerName);
      router.push("/players");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleJoin() {
    if (!chosenServerId || !nameInput) return;
    setBusy(true);
    setError(null);
    try {
      await api.joinServer(Number(chosenServerId), nameInput);
      setServerId(Number(chosenServerId));
      setActorName(nameInput);
      router.push("/players");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!loaded) return null;

  return (
    <div>
      <h1>AI Inhouse Balancer</h1>
      {serverId && actorName && (
        <p className="muted">
          현재: 서버 #{serverId} · {actorName} — <a href="/players">참가자 관리로 이동</a>
        </p>
      )}
      {error && <p className="error">{error}</p>}

      <div className="card">
        <h3>기존 서버 참가</h3>
        <div className="row">
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
          <input
            placeholder="내 이름"
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
          />
          <button onClick={handleJoin} disabled={busy || !chosenServerId || !nameInput}>
            참가
          </button>
        </div>
      </div>

      <div className="card">
        <h3>새 서버 만들기</h3>
        <div className="row">
          <input
            placeholder="새 서버 이름"
            value={newServerName}
            onChange={(e) => setNewServerName(e.target.value)}
          />
          <input
            placeholder="내 이름 (Owner가 됩니다)"
            value={ownerName}
            onChange={(e) => setOwnerName(e.target.value)}
          />
          <button onClick={handleCreateServer} disabled={busy || !newServerName || !ownerName}>
            서버 만들기
          </button>
        </div>
      </div>
    </div>
  );
}
