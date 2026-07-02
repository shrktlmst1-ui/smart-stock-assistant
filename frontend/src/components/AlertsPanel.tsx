import type { Alert } from "../types";

const ALERT_ICONS: Record<string, string> = {
  entry_opportunity: "📈",
  exit_opportunity: "📉",
  buy_alert: "🟢",
  sell_alert: "🔴",
  trap_warning: "⚠️",
  fake_pump_warning: "🚨",
  high_liquidity_no_confirm: "💧",
  info: "ℹ️",
};

interface Props {
  alerts: (Alert & { symbol: string })[];
}

export function AlertsPanel({ alerts }: Props) {
  return (
    <div className="card alerts-card">
      <div className="card-header">
        <h2>التنبيهات</h2>
        <span className="muted">{alerts.length}</span>
      </div>
      <div className="alerts-list">
        {alerts.length === 0 && <p className="muted empty">لا توجد تنبيهات حالياً</p>}
        {alerts.slice(0, 12).map((a, i) => (
          <div key={`${a.symbol}-${a.timestamp}-${i}`} className={`alert-item severity-${a.severity}`}>
            <span className="alert-icon">{ALERT_ICONS[a.alert_type] || "🔔"}</span>
            <div>
              <div className="alert-title">
                <strong>{a.symbol}</strong> — {a.title}
              </div>
              <div className="alert-msg">{a.message}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
