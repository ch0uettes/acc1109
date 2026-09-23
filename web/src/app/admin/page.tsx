"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  ApiError,
  ConstraintInfo,
  HardConstraintConfig,
  NormalizationConfig,
  RoleChange,
  Server,
  ServerMembership,
} from "@/lib/api";
import { useSession } from "@/lib/session";

export default function AdminPage() {
  const router = useRouter();
  const { serverId, actorName, loaded } = useSession();

  const [server, setServer] = useState<Server | null>(null);
  const [members, setMembers] = useState<ServerMembership[]>([]);
  const [history, setHistory] = useState<RoleChange[]>([]);
  const [constraints, setConstraints] = useState<ConstraintInfo[]>([]);

  const [promoteTarget, setPromoteTarget] = useState("");
  const [demoteTarget, setDemoteTarget] = useState("");
  const [transferTarget, setTransferTarget] = useState("");
  const [seasonLabel, setSeasonLabel] = useState("");
  const [norm, setNorm] = useState<NormalizationConfig | null>(null);
  const [hard, setHard] = useState<HardConstraintConfig | null>(null);
  const [priorities, setPriorities] = useState<Record<string, number>>({});

  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    if (!serverId) return;
    api.getServer(serverId).then((s) => {
      setServer(s);
      setSeasonLabel(s.current_season_label);
      setNorm(s.normalization_config);
      setHard(s.hard_constraint_config);
    }).catch((e) => setError(String(e)));
    api.listMembers(serverId).then(setMembers).catch(() => undefined);
    api.roleChangeHistory(serverId).then(setHistory).catch(() => undefined);
    api.listConstraints(serverId).then((list) => {
      setConstraints(list);
      setPriorities(Object.fromEntries(list.map((c) => [c.name, c.current_priority])));
    }).catch(() => undefined);
  }, [serverId]);

  useEffect(() => {
    if (loaded && (!serverId || !actorName)) {
      router.push("/");
      return;
    }
    refresh();
  }, [loaded, serverId, actorName, router, refresh]);

  async function run(action: () => Promise<unknown>, successMsg: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setInfo(successMsg);
      refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!loaded || !serverId || !actorName) return null;

  const players = members.filter((m) => m.role === "PLAYER").map((m) => m.display_name);
  const admins = members.filter((m) => m.role === "SERVER_ADMIN").map((m) => m.display_name);
  const others = members.filter((m) => m.display_name !== actorName).map((m) => m.display_name);

  return (
    <div>
      <h1>서버 관리</h1>
      {error && <p className="error">{error}</p>}
      {info && <p className="muted">{info}</p>}

      <div className="card">
        <h3>멤버 목록</h3>
        <table>
          <thead>
            <tr>
              <th>이름</th>
              <th>역할</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id}>
                <td>{m.display_name}</td>
                <td>{m.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>멤버 승급 (Server Admin)</h3>
        <div className="row">
          <input
            placeholder="대상 이름 (미등록자도 가능)"
            value={promoteTarget}
            onChange={(e) => setPromoteTarget(e.target.value)}
            list="player-names"
          />
          <datalist id="player-names">
            {players.map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>
          <button
            onClick={() =>
              run(() => api.promoteMember(serverId, actorName, promoteTarget), `${promoteTarget}을(를) 승급했습니다.`)
            }
            disabled={busy || !promoteTarget}
          >
            승급
          </button>
        </div>
      </div>

      {admins.length > 0 && (
        <div className="card">
          <h3>Server Admin 강등</h3>
          <div className="row">
            <select value={demoteTarget} onChange={(e) => setDemoteTarget(e.target.value)}>
              <option value="">대상 선택</option>
              {admins.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <button
              onClick={() =>
                run(() => api.demoteMember(serverId, actorName, demoteTarget), `${demoteTarget}을(를) 강등했습니다.`)
              }
              disabled={busy || !demoteTarget}
            >
              강등
            </button>
          </div>
        </div>
      )}

      {others.length > 0 && (
        <div className="card">
          <h3>Owner 이전</h3>
          <div className="row">
            <select value={transferTarget} onChange={(e) => setTransferTarget(e.target.value)}>
              <option value="">새 Owner 선택</option>
              {others.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <button
              onClick={() =>
                run(
                  () => api.transferOwnership(serverId, actorName, transferTarget),
                  `${transferTarget}에게 Owner를 이전했습니다.`
                )
              }
              disabled={busy || !transferTarget}
            >
              이전
            </button>
          </div>
        </div>
      )}

      <div className="card">
        <h3>현재 시즌 라벨</h3>
        <div className="row">
          <input value={seasonLabel} onChange={(e) => setSeasonLabel(e.target.value)} />
          <button
            onClick={() => run(() => api.updateSeasonLabel(serverId, actorName, seasonLabel), "시즌 라벨을 저장했습니다.")}
            disabled={busy}
          >
            저장
          </button>
        </div>
      </div>

      {norm && hard && (
        <div className="card">
          <h3>밸런스 계산 설정</h3>
          <p className="muted">기본값은 이 앱의 Rating 스케일에 맞춰져 있습니다. 필요할 때만 조정하세요.</p>
          <div className="row" style={{ flexWrap: "wrap", gap: 12 }}>
            {(
              [
                ["mean_balance_midpoint", "전체 평균 균형 - 중심점"],
                ["mean_balance_steepness", "전체 평균 균형 - 기울기"],
                ["outlier_penalty_midpoint", "극단 팀 페널티 - 중심점"],
                ["outlier_penalty_steepness", "극단 팀 페널티 - 기울기"],
                ["internal_rating_midpoint", "내전 Rating 격차 - 중심점"],
                ["internal_rating_steepness", "내전 Rating 격차 - 기울기"],
                ["lane_difference_max", "라인별 격차 상한"],
                ["team_variance_scale", "팀 내부 분산 스케일"],
                ["role_penalty_max", "포지션 페널티 상한"],
              ] as [keyof NormalizationConfig, string][]
            ).map(([key, label]) => (
              <label key={key} style={{ display: "flex", flexDirection: "column", gap: 4, width: 220 }}>
                <span className="muted">{label}</span>
                <input
                  type="number"
                  value={norm[key] as number}
                  onChange={(e) => setNorm({ ...norm, [key]: Number(e.target.value) })}
                />
              </label>
            ))}
          </div>

          <h4 style={{ marginTop: 16 }}>Hard Constraint (비워두면 비활성)</h4>
          <div className="row" style={{ flexWrap: "wrap", gap: 12 }}>
            {(
              [
                ["mean_balance_diff_max", "전체 평균 균형 상한"],
                ["lane_diff_max", "라인별 격차 상한"],
                ["team_variance_max", "팀 내부 분산 상한"],
                ["minimum_main_role_ratio", "Main 포지션 최소 비율"],
              ] as [keyof HardConstraintConfig, string][]
            ).map(([key, label]) => (
              <label key={key} style={{ display: "flex", flexDirection: "column", gap: 4, width: 220 }}>
                <span className="muted">{label}</span>
                <input
                  type="number"
                  value={hard[key] ?? ""}
                  placeholder="비활성"
                  onChange={(e) =>
                    setHard({ ...hard, [key]: e.target.value === "" ? null : Number(e.target.value) })
                  }
                />
              </label>
            ))}
          </div>

          <div className="row" style={{ marginTop: 12 }}>
            <button
              onClick={() =>
                run(() => api.updateBalanceConfig(serverId, actorName, norm, hard), "밸런스 설정을 저장했습니다.")
              }
              disabled={busy}
            >
              저장
            </button>
          </div>
        </div>
      )}

      {constraints.length > 0 && (
        <div className="card">
          <h3>Constraint 우선순위</h3>
          {constraints.map((c) => (
            <div key={c.name} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
              <div>
                <strong>{c.name}</strong>
                <div className="muted">
                  {c.description} · {c.tier} · {c.pipeline} · 기본 {c.default_priority}
                </div>
              </div>
              <input
                type="number"
                style={{ width: 80 }}
                value={priorities[c.name] ?? c.default_priority}
                onChange={(e) => setPriorities({ ...priorities, [c.name]: Number(e.target.value) })}
              />
            </div>
          ))}
          <button
            onClick={() =>
              run(
                () => api.updateConstraintPriorities(serverId, actorName, priorities),
                "Constraint 우선순위를 저장했습니다."
              )
            }
            disabled={busy}
          >
            저장
          </button>
        </div>
      )}

      <div className="card">
        <h3>역할 변경 이력</h3>
        {history.length === 0 ? (
          <p className="muted">아직 역할 변경 이력이 없습니다.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>시각</th>
                <th>대상</th>
                <th>이전 역할</th>
                <th>변경 후 역할</th>
                <th>변경자</th>
              </tr>
            </thead>
            <tbody>
              {[...history].reverse().map((h) => (
                <tr key={h.id}>
                  <td>{new Date(h.changed_at).toLocaleString()}</td>
                  <td>{h.target_display_name}</td>
                  <td>{h.old_role ?? "-"}</td>
                  <td>{h.new_role}</td>
                  <td>{h.changed_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
