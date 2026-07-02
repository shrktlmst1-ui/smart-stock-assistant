import type { PerformanceMetrics } from "../types";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="perf-stat">
      <span className="muted">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function PerformancePanel({ metrics }: { metrics: PerformanceMetrics | null }) {
  if (!metrics) {
    return (
      <div className="card performance-card">
        <div className="card-header"><h2>Performance Dashboard</h2></div>
        <p className="muted">Loading performance metrics...</p>
      </div>
    );
  }

  return (
    <div className="card performance-card">
      <div className="card-header">
        <h2>Performance Dashboard</h2>
        <span className="badge status-buy">{metrics.win_rate.toFixed(1)}% Win Rate</span>
      </div>
      <div className="perf-grid">
        <Stat label="Win Rate" value={`${metrics.win_rate.toFixed(1)}%`} />
        <Stat label="Today's Trades" value={metrics.today_trades} />
        <Stat label="Weekly Trades" value={metrics.weekly_trades} />
        <Stat label="Monthly Trades" value={metrics.monthly_trades} />
        <Stat label="Total Profit" value={`+${metrics.total_profit_pct.toFixed(2)}%`} />
        <Stat label="Total Loss" value={`-${metrics.total_loss_pct.toFixed(2)}%`} />
        <Stat label="Net P/L" value={`${metrics.net_profit_pct >= 0 ? "+" : ""}${metrics.net_profit_pct.toFixed(2)}%`} />
        <Stat label="Avg Confidence" value={`${metrics.average_confidence.toFixed(1)}%`} />
        <Stat label="Best Strategy" value={metrics.best_performing_strategy} />
        <Stat label="Wins / Losses" value={`${metrics.wins} / ${metrics.losses}`} />
        <Stat label="Open Trades" value={metrics.open_trades} />
        <Stat label="Closed Trades" value={metrics.total_trades} />
      </div>
    </div>
  );
}
