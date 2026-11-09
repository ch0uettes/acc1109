"use client";

import { useEffect, useRef, useState } from "react";
import { formatUtc } from "@/lib/time";

export interface RatingPoint {
  label: string; // "시작" or a match label
  played_at: string | null;
  rating: number;
  delta: number | null;
  won: boolean | null;
}

// Single series (one player's internal rating after each match): no legend,
// the card title names it. Hover anywhere picks the nearest match.
// Drawn at the container's real pixel width (not a scaled viewBox) so axis
// text stays 12px on a phone.
const DEFAULT_W = 640;
const H = 220;
const PAD = { top: 16, right: 16, bottom: 28, left: 44 };

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) return [min];
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) ticks.push(Number(v.toFixed(6)));
  return ticks;
}

export default function RatingChart({ points }: { points: RatingPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(DEFAULT_W);
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const measure = () => setW(Math.max(280, Math.round(el.clientWidth)));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  if (points.length < 2) return null;

  const values = points.map((p) => p.rating);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (hi - lo < 1) {
    lo -= 0.5;
    hi += 0.5;
  }
  const padY = (hi - lo) * 0.1;
  lo -= padY;
  hi += padY;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo)) * plotH;
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.rating).toFixed(1)}`).join(" ");
  const ticks = niceTicks(lo, hi);

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const vx = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((vx - PAD.left) / plotW) * (points.length - 1));
    setHover(Math.max(0, Math.min(points.length - 1, i)));
  }

  const hp = hover !== null ? points[hover] : null;

  return (
    <div className="rating-chart" ref={boxRef}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width={W}
        height={H}
        role="img"
        aria-label={`내부 레이팅 변화: ${values[0].toFixed(1)}에서 ${values[values.length - 1].toFixed(1)}`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} className="rc-grid" />
            <text x={PAD.left - 8} y={y(t)} className="rc-axis" textAnchor="end" dominantBaseline="middle">
              {t.toFixed(Math.abs(hi - lo) < 5 ? 1 : 0)}
            </text>
          </g>
        ))}
        <text x={PAD.left} y={H - 8} className="rc-axis">
          {points[0].label}
        </text>
        <text x={W - PAD.right} y={H - 8} className="rc-axis" textAnchor="end">
          {points[points.length - 1].label}
        </text>
        {hover !== null && (
          <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={H - PAD.bottom} className="rc-crosshair" />
        )}
        <path d={path} className="rc-line" />
        {points.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.rating)} r={hover === i ? 6 : 4} className="rc-dot" />
        ))}
        {/* Wide transparent hit area so hovering anywhere in the plot works. */}
        <rect x={PAD.left} y={PAD.top} width={plotW} height={plotH} fill="transparent" />
      </svg>
      {hp && hover !== null && (
        <div
          className="rc-tooltip"
          style={{
            left: `${(x(hover) / W) * 100}%`,
            top: `${(y(hp.rating) / H) * 100}%`,
            transform: `translate(${hover > points.length / 2 ? "calc(-100% - 12px)" : "12px"}, -50%)`,
          }}
        >
          <strong>{hp.label}</strong>
          {hp.played_at && <div className="muted">{formatUtc(hp.played_at)}</div>}
          <div>
            내부 레이팅 {hp.rating.toFixed(1)}
            {hp.delta !== null && ` (${hp.delta >= 0 ? "+" : ""}${hp.delta.toFixed(1)})`}
          </div>
          {hp.won !== null && <div>{hp.won ? "승" : "패"}</div>}
        </div>
      )}
    </div>
  );
}
