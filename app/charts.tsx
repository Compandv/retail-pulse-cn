import { useId } from "react";
import type { HistoryPoint } from "./types";
const formatDate = (value: string) => value ? value.slice(5).replace("-", "/") : "—";

export function LineChart({ points, metric = "overall" }: { points: Array<Partial<HistoryPoint> & { date: string }>; metric?: keyof HistoryPoint }) {
  const width = 760;
  const height = 238;
  const padX = 36;
  const padY = 22;
  const chartId = useId().replace(/:/g, "");
  const values = points.map(point => {
    const raw = point[metric];
    return typeof raw === "number" && Number.isFinite(raw) ? raw : null;
  });
  if (!points.length || values.every(value => value === null)) return <div className="empty-state">这个时间段还没有可比较的观测数据。</div>;
  const isDirection = metric === "direction";
  const domainMin = isDirection ? -100 : 0;
  const domainMax = 100;
  const x = (index: number) => padX + (index / Math.max(points.length - 1, 1)) * (width - padX * 2);
  const y = (value: number) =>
    padY + ((domainMax - value) / (domainMax - domainMin)) * (height - padY * 2);
  const path = values.map((value, index) => value === null ? "" : `${index === 0 || values[index - 1] === null ? "M" : "L"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
  const area = `${path} L${x(values.length - 1).toFixed(1)},${y(domainMin).toFixed(1)} L${x(0).toFixed(1)},${y(domainMin).toFixed(1)} Z`;
  const neutralY = y(isDirection ? 0 : 50);

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`最近 ${points.length} 个有观测交易日情绪趋势`}>
        <defs>
          <linearGradient id={`area-${chartId}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e85432" stopOpacity="0.24" />
            <stop offset="100%" stopColor="#e85432" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line key={ratio} x1={padX} x2={width - padX} y1={padY + ratio * (height - padY * 2)} y2={padY + ratio * (height - padY * 2)} className="grid-line" />
        ))}
        <line x1={padX} x2={width - padX} y1={neutralY} y2={neutralY} className="neutral-line" />
        {[domainMax, isDirection ? 0 : 50, domainMin].map(value => <text key={value} x={0} y={y(value) + 4} fill="currentColor" opacity={0.65} fontSize={13}>{value}</text>)}
        {!isDirection && values.every(value => value !== null) && <path d={area} fill={`url(#area-${chartId})`} />}
        <path d={path} className="trend-line" />
        {values.map((value, index) => value === null ? null : (
          <circle key={`${points[index].date}-${value}`} cx={x(index)} cy={y(value)} r={index === values.length - 1 ? 4.6 : 2.1} className={index === values.length - 1 ? "last-dot" : "trend-dot"}>
            <title>{`${points[index].date}：${value.toFixed(1)}（${points[index].recordType === "estimated" ? "历史估算" : points[index].recordType === "measured" ? "实测" : "观测"}）`}</title>
          </circle>
        ))}
      </svg>
      <div className="chart-axis" aria-hidden="true">
        <span>{formatDate(points[0]?.date ?? "")}</span>
        <span>{formatDate(points[Math.floor(points.length / 2)]?.date ?? "")}</span>
        <span>{formatDate(points[points.length - 1]?.date ?? "")}</span>
      </div>
    </div>
  );
}

export function HeatSparkline({ points }: { points: Array<{ date: string; value: number }> }) {
  if (!points.length) return <div className="sparkline empty">等待每日数据</div>;
  const width = 220;
  const height = 42;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = Math.max(8, max - min);
  const x = (index: number) => (index / Math.max(1, points.length - 1)) * width;
  const y = (value: number) => 5 + ((max - value) / spread) * (height - 10);
  const path = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ");
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="板块最近热度轨迹">
      {points.length > 1 && <path d={path} />}
      {points.map((point, index) => <circle key={point.date} cx={x(index)} cy={y(point.value)} r={index === points.length - 1 ? 3 : 2}><title>{`${point.date}：${point.value.toFixed(1)}`}</title></circle>)}
    </svg>
  );
}
