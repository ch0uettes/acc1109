import type { Metadata } from "next";
import "./globals.css";
import Nav from "./nav";

export const metadata: Metadata = {
  title: "AI Inhouse Balancer",
  description: "내전 밸런싱 AI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <Nav />
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
