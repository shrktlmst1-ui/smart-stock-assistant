import type { DashboardMeters } from "../types";

function MeterBar({ label, value = 0, invert }: { label: string; value?: number; invert?: boolean }) {
  const safe = Number.isFinite(value) ? value : 0;
  const display = invert ? 100 - safe : safe;
  const color =
    label === "Market Risk"
      ? safe > 60
        ? "var(--red)"
        : safe > 35
          ? "var(--orange)"
          : "var(--green)"
      : "var(--accent)";

  return (
    <div className="meter-item">
      <div className="meter-header">
        <span className="muted">{label}</span>
        <strong>{safe.toFixed(0)}%</strong>
      </div>
      <div className="meter-track">
        <div className="meter-fill" style={{ width: `${display}%`, background: color }} />
      </div>
    </div>
  );
}

export function MetersPanel({ meters }: { meters: DashboardMeters | null }) {
  if (!meters) return null;

  return (
    <div className="card meters-card">
      <div className="card-header">
        <h2>Institutional Meters</h2>
      </div>
      <div className="meters-grid">
        <MeterBar label="Smart Money" value={meters.smart_money_meter} />
        <MeterBar label="Liquidity" value={meters.liquidity_meter} />
        <MeterBar label="Trend Strength" value={meters.trend_strength} />
        <MeterBar label="Market Risk" value={meters.market_risk} invert />
        <MeterBar label="Institutional Activity" value={meters.institutional_activity} />
        <MeterBar label="AI Confidence" value={meters.ai_confidence} />
      </div>
    </div>
  );
}
