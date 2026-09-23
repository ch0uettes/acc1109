import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Inhouse Balancer",
  description: "내전 밸런싱 AI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <nav className="nav">
          <div>
            <Link href="/">서버 선택</Link>
            <Link href="/players">참가자 관리</Link>
            <Link href="/teams">팀 생성</Link>
            <Link href="/matches">경기 저장</Link>
          </div>
        </nav>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
