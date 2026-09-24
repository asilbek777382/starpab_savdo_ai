import { useState } from "react";

/** Bitta ko'rsatkichning kunlik ustunli grafigi (small multiples uchun). SVG, kutubxonasiz. */
export function DailyBars({ title, points, color }: { title: string; points: { date: string; value: number }[]; color: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 320;
  const H = 120;
  const PAD_B = 18;
  const plotH = H - PAD_B - 6;
  const max = Math.max(1, ...points.map((p) => p.value));
  const step = W / Math.max(points.length, 1);
  const barW = Math.max(2, step - 2); // 2px oraliq
  const total = points.reduce((s, p) => s + p.value, 0);
  // "2026-09-24" → "24.09" (locale formatlariga bog'liq bo'lmasligi uchun)
  const fmtDay = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

  return (
    <figure className="relative">
      <figcaption className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-medium text-slate-700">{title}</span>
        <span className="text-lg font-semibold text-slate-900">{total}</span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-32 w-full" role="img" aria-label={`${title}: ${total}`} onMouseLeave={() => setHover(null)}>
        <line x1="0" x2={W} y1={6} y2={6} stroke="#e2e8f0" strokeDasharray="3 3" />
        <text x={W} y={4} textAnchor="end" className="fill-slate-400" fontSize="9">
          {max}
        </text>
        <line x1="0" x2={W} y1={H - PAD_B} y2={H - PAD_B} stroke="#cbd5e1" />
        {points.map((p, i) => {
          const h = (p.value / max) * plotH;
          const x = i * step + 1;
          const y = H - PAD_B - h;
          const r = Math.min(4, barW / 2, h);
          const d =
            h <= 0
              ? ""
              : `M${x},${H - PAD_B} V${y + r} Q${x},${y} ${x + r},${y} H${x + barW - r} Q${x + barW},${y} ${x + barW},${y + r} V${H - PAD_B} Z`;
          return (
            <g key={p.date} onMouseEnter={() => setHover(i)}>
              <rect x={i * step} y={0} width={step} height={H - PAD_B} fill="transparent" />
              {d && <path d={d} fill={color} opacity={hover === null || hover === i ? 1 : 0.45} />}
            </g>
          );
        })}
        {[0, Math.floor((points.length - 1) / 2), points.length - 1].map((i) =>
          points[i] ? (
            <text key={i} x={i * step + step / 2} y={H - 4} fontSize="9" textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"} className="fill-slate-500">
              {fmtDay(points[i].date)}
            </text>
          ) : null,
        )}
      </svg>
      {hover !== null && points[hover] && (
        <div
          className="pointer-events-none absolute top-8 rounded-lg bg-ink px-2.5 py-1.5 text-xs text-white shadow-lg"
          style={{ left: `clamp(0px, calc(${((hover + 0.5) / points.length) * 100}% - 40px), calc(100% - 80px))` }}
        >
          <div className="text-slate-300">{fmtDay(points[hover].date)}</div>
          <div className="font-semibold">{points[hover].value}</div>
        </div>
      )}
    </figure>
  );
}
