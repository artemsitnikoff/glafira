import { useId } from 'react';
import type { ReactNode } from 'react';

/**
 * Рендер одной ячейки матрицы «Логика» — чёрно-белая геометрия из params.
 *
 * ⚠️ Механизм — как в эталоне (project/«Тесты - кандидат.html»): inline SVG, viewBox 0..100,
 *     фигура строится словарём shape/fill. Здесь он РАСШИРЕН до полного домена params из
 *     backend/app/seed_tests.py (shape/fill/size/count/rot/lines + inner-маркеры), чтобы
 *     нарисовать ЛЮБУЮ ячейку, которую отдаёт API.
 *
 * ⚠️ ЦВЕТ НЕ ИСПОЛЬЗУЕТСЯ. Вся «краска» — единый ink = var(--ark-gray-800) (#1F2733),
 *     заданный через `color` на .mx-svg и currentColor внутри. Различие несут форма,
 *     контур, штриховка (hatch-h / hatch-v / dots) и сплошная заливка — не цвет.
 *
 * Один и тот же компонент рисует и ячейки матрицы-вопроса, и 8 вариантов ответа.
 */

export type CellParams = {
  shape?: string | null;
  fill?: string | null;
  size?: string | null;
  count?: number | null;
  rot?: number | null;
  lines?: string[] | null;
};

function clamp(min: number, v: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

/** Точки правильного многоугольника (sides вершин), стартовый угол startDeg. */
function regularPolygon(cx: number, cy: number, r: number, sides: number, startDeg: number): string {
  const pts: string[] = [];
  for (let i = 0; i < sides; i++) {
    const a = ((startDeg + (i * 360) / sides) * Math.PI) / 180;
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return pts.join(' ');
}

/** Точки пятиконечной звезды. */
function starPoints(cx: number, cy: number, rO: number, rI: number, points: number, startDeg: number): string {
  const out: string[] = [];
  for (let i = 0; i < points * 2; i++) {
    const r = i % 2 === 0 ? rO : rI;
    const a = ((startDeg + (i * 180) / points) * Math.PI) / 180;
    out.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return out.join(' ');
}

type StrokeFill = { fill: string; stroke: string; strokeWidth: number; strokeLinejoin: 'round' };

/** Одна фигура shape в центре (cx, cy) радиуса r. */
function shapeEl(shape: string, cx: number, cy: number, r: number, fill: string, sw: number, key: string): ReactNode {
  const common: StrokeFill = { fill, stroke: 'currentColor', strokeWidth: sw, strokeLinejoin: 'round' };
  switch (shape) {
    case 'circle':
      return <circle key={key} cx={cx} cy={cy} r={r} {...common} />;
    case 'square':
      return <rect key={key} x={cx - r} y={cy - r} width={2 * r} height={2 * r} rx={3} {...common} />;
    case 'triangle':
      return <polygon key={key} points={regularPolygon(cx, cy, r, 3, -90)} {...common} />;
    case 'diamond':
      return <polygon key={key} points={regularPolygon(cx, cy, r, 4, -90)} {...common} />;
    case 'hexagon':
      return <polygon key={key} points={regularPolygon(cx, cy, r, 6, -90)} {...common} />;
    case 'star':
      return <polygon key={key} points={starPoints(cx, cy, r, r * 0.42, 5, -90)} {...common} />;
    case 'key':
      return keyEl(cx, cy, r, fill, sw, key);
    default:
      return null;
  }
}

/** Ключ — асимметричная фигура (голова-кольцо + стержень с бородкой справа), чтобы был виден поворот. */
function keyEl(cx: number, cy: number, r: number, fill: string, sw: number, key: string): ReactNode {
  const headR = r * 0.42;
  const headY = cy - r * 0.48;
  const line = {
    stroke: 'currentColor',
    strokeWidth: sw * 1.5,
    fill: 'none',
    strokeLinecap: 'round' as const,
  };
  return (
    <g key={key}>
      <circle cx={cx} cy={headY} r={headR} fill={fill} stroke="currentColor" strokeWidth={sw} />
      <line x1={cx} y1={headY + headR} x2={cx} y2={cy + r} {...line} />
      <line x1={cx} y1={cy + r * 0.5} x2={cx + r * 0.34} y2={cy + r * 0.5} {...line} />
      <line x1={cx} y1={cy + r * 0.86} x2={cx + r * 0.24} y2={cy + r * 0.86} {...line} />
    </g>
  );
}

/** Линия-фигура внутри ячейки (vert / horiz / diag / arc). */
function lineEl(kind: string, key: string): ReactNode {
  const p = { stroke: 'currentColor', strokeWidth: 4, fill: 'none', strokeLinecap: 'round' as const };
  switch (kind) {
    case 'vert':
      return <line key={key} x1={50} y1={16} x2={50} y2={84} {...p} />;
    case 'horiz':
      return <line key={key} x1={16} y1={50} x2={84} y2={50} {...p} />;
    case 'diag-l':
      return <line key={key} x1={20} y1={20} x2={80} y2={80} {...p} />;
    case 'diag-r':
      return <line key={key} x1={80} y1={20} x2={20} y2={80} {...p} />;
    case 'arc-top':
      return <path key={key} d="M20 60 Q50 16 80 60" {...p} />;
    case 'arc-bottom':
      return <path key={key} d="M20 40 Q50 84 80 40" {...p} />;
    default:
      return null;
  }
}

/** Внутренний маркер D2 (dot / cross) в центре — НЕ вращается, чтобы оставаться стабильным. */
function innerEl(marker: string, key: string): ReactNode {
  const val = marker.slice('inner:'.length);
  if (val === 'dot') {
    return <circle key={key} cx={50} cy={50} r={7} fill="currentColor" />;
  }
  if (val === 'cross') {
    const p = { stroke: 'currentColor', strokeWidth: 4.5, strokeLinecap: 'round' as const };
    return (
      <g key={key}>
        <line x1={42} y1={42} x2={58} y2={58} {...p} />
        <line x1={58} y1={42} x2={42} y2={58} {...p} />
      </g>
    );
  }
  return null;
}

/** Паттерн заливки (штриховка/точки) — тоже монохром, ink = currentColor. */
function patternDef(kind: string, id: string): ReactNode {
  if (kind === 'dots') {
    return (
      <pattern id={id} width={8} height={8} patternUnits="userSpaceOnUse">
        <circle cx={4} cy={4} r={1.5} fill="currentColor" />
      </pattern>
    );
  }
  if (kind === 'hatch-v') {
    return (
      <pattern id={id} width={7} height={7} patternUnits="userSpaceOnUse">
        <line x1={3.5} y1={0} x2={3.5} y2={7} stroke="currentColor" strokeWidth={1.7} />
      </pattern>
    );
  }
  // hatch-h — горизонтальные линии
  return (
    <pattern id={id} width={7} height={7} patternUnits="userSpaceOnUse">
      <line x1={0} y1={3.5} x2={7} y2={3.5} stroke="currentColor" strokeWidth={1.7} />
    </pattern>
  );
}

export function MatrixCell({ params }: { params: CellParams }) {
  const rawId = useId();
  const patternId = `mxp-${rawId.replace(/[:]/g, '')}`;

  const fillKind = params.fill ?? null;
  const needsPattern = fillKind === 'hatch-h' || fillKind === 'hatch-v' || fillKind === 'dots';
  const fillAttr = fillKind === 'solid' ? 'currentColor' : needsPattern ? `url(#${patternId})` : 'none';

  const allLines = params.lines ?? [];
  const figureLines = allLines.filter((l) => !l.startsWith('inner:'));
  const innerMarkers = allLines.filter((l) => l.startsWith('inner:'));

  const rot = params.rot ?? 0;

  const shapeEls: ReactNode[] = [];
  if (params.shape) {
    const n = params.count === 2 ? 2 : params.count === 3 ? 3 : 1;
    const centers = n === 1 ? [50] : n === 2 ? [30, 70] : [22, 50, 78];
    const slotHalf = n === 1 ? 34 : n === 2 ? 20 : 14;
    const sizeMult = params.size === 'S' ? 0.72 : params.size === 'L' ? 1.0 : params.size === 'M' ? 0.9 : 0.95;
    const r = slotHalf * sizeMult;
    const sw = clamp(2.2, r * 0.09, 3.2);
    centers.forEach((cx, i) => {
      shapeEls.push(shapeEl(params.shape as string, cx, 50, r, fillAttr, sw, `s${i}`));
    });
  }

  const lineEls = figureLines.map((l, i) => lineEl(l, `l${i}`));
  const innerEls = innerMarkers.map((m, i) => innerEl(m, `i${i}`));

  return (
    <svg viewBox="0 0 100 100" className="mx-svg" aria-hidden="true" preserveAspectRatio="xMidYMid meet">
      {needsPattern && <defs>{patternDef(fillKind as string, patternId)}</defs>}
      <g transform={rot ? `rotate(${rot} 50 50)` : undefined}>
        {shapeEls}
        {lineEls}
      </g>
      {innerEls}
    </svg>
  );
}
