"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { syncSession, useSession } from "@/lib/session";

// Client component so the 서버 관리 link can follow the logged-in role -
// hiding it is only a UI nicety, the API enforces the permission itself.
export default function Nav() {
  const { serverId, actorName, isAdmin } = useSession();
  const pathname = usePathname();

  // Re-read role and name from the server on each page change (the nav
  // never remounts), so a demotion or rename shows without re-entering.
  // A revoked token gets the usual 401 handling in api.ts.
  useEffect(() => {
    if (!serverId) return;
    api.me(serverId).then(syncSession).catch(() => undefined);
  }, [serverId, pathname]);

  return (
    <nav className="nav">
      <div className="nav-links">
        <Link href="/">서버 선택</Link>
        <Link href="/players">참가자 관리</Link>
        <Link href="/teams">팀 생성</Link>
        <Link href="/matches">경기 저장</Link>
        <Link href="/votes">MVP 투표</Link>
        <Link href="/stats">통계</Link>
        {isAdmin && <Link href="/admin">서버 관리</Link>}
      </div>
      {actorName && <span className="muted">{actorName}</span>}
    </nav>
  );
}
