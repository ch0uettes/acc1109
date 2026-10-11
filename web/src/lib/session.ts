"use client";

// Login state from POST /servers/{id}/session (entry code, plus PIN for
// admins) - persisted in localStorage. The token is the only thing the
// backend trusts: it re-reads the Role from the DB on every request (see
// app/api/deps.py), so the role kept here only decides what the UI
// shows, never what the API allows.
import { useEffect, useState } from "react";
import type { Role, ServerMembership } from "./api";

const SERVER_ID_KEY = "balancer.serverId";
const ACTOR_NAME_KEY = "balancer.actorName";
const ROLE_KEY = "balancer.role";
export const TOKEN_KEY = "balancer.token";
// Fired on every login/logout so every mounted useSession() (the nav bar
// included, which never remounts between pages) picks up the change.
const SESSION_EVENT = "balancer-session";

export const ADMIN_ROLES: Role[] = ["OWNER", "SERVER_ADMIN"];

export function readToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveSession(member: ServerMembership, token: string) {
  window.localStorage.setItem(SERVER_ID_KEY, String(member.server_id));
  window.localStorage.setItem(ACTOR_NAME_KEY, member.display_name);
  window.localStorage.setItem(ROLE_KEY, member.role);
  window.localStorage.setItem(TOKEN_KEY, token);
  window.dispatchEvent(new Event(SESSION_EVENT));
}

export function clearSession() {
  for (const key of [SERVER_ID_KEY, ACTOR_NAME_KEY, ROLE_KEY, TOKEN_KEY]) {
    window.localStorage.removeItem(key);
  }
  window.dispatchEvent(new Event(SESSION_EVENT));
}

export function useSession() {
  const [serverId, setServerId] = useState<number | null>(null);
  const [actorName, setActorName] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const load = () => {
      // No token = not logged in, whatever else is left over (e.g. a
      // pre-login-era serverId/actorName from before this shipped).
      const token = window.localStorage.getItem(TOKEN_KEY);
      const storedServerId = window.localStorage.getItem(SERVER_ID_KEY);
      setServerId(token && storedServerId ? Number(storedServerId) : null);
      setActorName(token ? window.localStorage.getItem(ACTOR_NAME_KEY) : null);
      setRole(token ? (window.localStorage.getItem(ROLE_KEY) as Role | null) : null);
      setLoaded(true);
    };
    load();
    window.addEventListener(SESSION_EVENT, load);
    window.addEventListener("storage", load);
    return () => {
      window.removeEventListener(SESSION_EVENT, load);
      window.removeEventListener("storage", load);
    };
  }, []);

  const isAdmin = role !== null && ADMIN_ROLES.includes(role);
  return { serverId, actorName, role, isAdmin, loaded, clear: clearSession };
}
