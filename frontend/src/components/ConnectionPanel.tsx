import type { ConnectionStatus } from "../types";

function StatusRow({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok?: boolean;
}) {
  return (
    <div className="status-row">
      <span className="muted">{label}</span>
      <span className={ok === true ? "ok" : ok === false ? "fail" : ""}>{value}</span>
    </div>
  );
}

export function ConnectionPanel({ status }: { status: ConnectionStatus | null }) {
  if (!status) {
    return (
      <div className="card connection-card">
        <div className="card-header">
          <h2>حالة الاتصال</h2>
        </div>
        <p className="muted empty">جاري التحقق من الاتصال...</p>
      </div>
    );
  }

  const authOk = status.authentication_status === "authenticated";
  const liveOk = status.live_market_data_status === "live";

  return (
    <div className="card connection-card">
      <div className="card-header">
        <h2>حالة الاتصال</h2>
        <span className={`badge ${liveOk ? "status-buy" : "status-wait"}`}>
          {status.stream_mode === "websocket" ? "WebSocket" : "REST Polling"}
        </span>
      </div>
      <div className="connection-grid">
        <StatusRow
          label="API Connected"
          value={status.api_connected ? "متصل" : "غير متصل"}
          ok={status.api_connected}
        />
        <StatusRow
          label="Authentication"
          value={status.authentication_status}
          ok={authOk}
        />
        <StatusRow
          label="Subscription"
          value={status.subscription_status}
          ok={authOk}
        />
        <StatusRow
          label="Live Market Data"
          value={status.live_market_data_status}
          ok={liveOk}
        />
        <StatusRow label="Plan" value={status.plan} />
        <StatusRow
          label="Symbols OK"
          value={`${status.symbols_ok.length}/${status.symbols_tested.length}`}
          ok={status.symbols_failed.length === 0}
        />
      </div>
      {status.symbols_ok.length > 0 && (
        <div className="symbol-chips">
          {status.symbols_ok.map((s) => (
            <span key={s} className="chip ok-chip">{s}</span>
          ))}
          {status.symbols_failed.map((s) => (
            <span key={s} className="chip fail-chip">{s}</span>
          ))}
        </div>
      )}
      {status.errors.length > 0 && (
        <div className="errors-box">
          {status.errors.map((e, i) => (
            <small key={i}>{e}</small>
          ))}
        </div>
      )}
    </div>
  );
}
