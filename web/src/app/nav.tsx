"use client";

import Link from "next/link";
import { useSession } from "@/lib/session";

// Client component so the 서버 관리 link can follow the logged-in role -
// hiding it is only a UI nicety, the API enforces the permission itself.
export default function Nav() {
  const { actorName, isAdmin } = useSession();

  return (
    <nav className="nav">
      <div>
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
