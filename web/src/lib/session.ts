"use client";

// Same "pick a name, no password" identity model as the Streamlit
// sidebar's server/actor picker (see DEPLOY.md) - just persisted in
// localStorage instead of st.session_state. The server never trusts this
// value for permissions; every write endpoint re-resolves the actor's
// Role from ServerMembership server-side (see app/api/deps.py).
import { useEffect, useState } from "react";

const SERVER_ID_KEY = "balancer.serverId";
const ACTOR_NAME_KEY = "balancer.actorName";

export function useSession() {
  const [serverId, setServerIdState] = useState<number | null>(null);
  const [actorName, setActorNameState] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const storedServerId = window.localStorage.getItem(SERVER_ID_KEY);
    const storedActorName = window.localStorage.getItem(ACTOR_NAME_KEY);
    setServerIdState(storedServerId ? Number(storedServerId) : null);
    setActorNameState(storedActorName);
    setLoaded(true);
  }, []);

  const setServerId = (id: number) => {
    window.localStorage.setItem(SERVER_ID_KEY, String(id));
    setServerIdState(id);
  };
  const setActorName = (name: string) => {
    window.localStorage.setItem(ACTOR_NAME_KEY, name);
    setActorNameState(name);
  };
  const clear = () => {
    window.localStorage.removeItem(SERVER_ID_KEY);
    window.localStorage.removeItem(ACTOR_NAME_KEY);
    setServerIdState(null);
    setActorNameState(null);
  };

  return { serverId, actorName, loaded, setServerId, setActorName, clear };
}
