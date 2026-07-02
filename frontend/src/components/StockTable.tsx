import type { MarketScanState, StockSnapshot } from "../types";
import { formatPrice } from "./StatusBadge";

interface Props {
  stocks: StockSnapshot[];
  selected: string | null;
  onSelect: (symbol: string) => void;
  scanState?: MarketScanState | null;
}

export function StockTable({ stocks, selected, onSelect, scanState }: Props) {
  const ub = scanState?.universe_breakdown;
  const universeLabel = ub
    ? `NYSE ${ub.NYSE ?? 0} · NASDAQ ${ub.NASDAQ ?? 0} · AMEX ${ub.AMEX ?? 0} · ETF ${ub.ETF ?? 0}`
    : scanState?.universe_size?.toLocaleString() ?? "—";

  return (
    <div className="card table-card institutional-dashboard">
      <div className="card-header">
        <h2>Professional Decision Engine — Top 20</h2>
        <span className="muted">
          {stocks.length}/20 institutional-grade · {universeLabel} · refresh {scanState?.scan_interval_seconds ?? 15}s
        </span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>AI Score</th>
              <th>Signal</th>
              <th>Conf</th>
              <th>Entry</th>
              <th>Stop</th>
              <th>TP1</th>
              <th>TP2</th>
              <th>R:R</th>
              <th>Hold</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((s) => {
              const td = s.trade_decision;
              const signal = td?.professional_signal ?? td?.recommendation ?? s.ai_signal.signal;
              const aiScore = td?.professional_ai_score ?? s.ai_signal.ai_score;
              const entry = td?.entry_zone_high ?? s.ai_signal.entry;
              const reason = td?.ai_explanation ?? td?.trigger_reason ?? s.ai_signal.reason;
              const signalCls =
                signal === "BUY" ? "ai-strong-buy"
                  : signal === "SELL" ? "ai-strong-sell"
                  : signal === "AVOID" ? "ai-strong-sell"
                  : "ai-wait";
              return (
                <tr
                  key={s.symbol}
                  className={selected === s.symbol ? "selected" : ""}
                  onClick={() => onSelect(s.symbol)}
                >
                  <td>
                    <strong>{s.symbol}</strong>
                    <small>{s.name}</small>
                  </td>
                  <td>{aiScore.toFixed(0)}</td>
                  <td>
                    <span className={`ai-tag ${signalCls}`}>{signal}</span>
                  </td>
                  <td>{(td?.ai_confidence ?? s.ai_signal.confidence).toFixed(0)}%</td>
                  <td>${formatPrice(entry)}</td>
                  <td>${formatPrice(td?.stop_loss ?? s.ai_signal.stop_loss)}</td>
                  <td>${formatPrice(td?.take_profit_1 ?? s.ai_signal.target_1)}</td>
                  <td>${formatPrice(td?.take_profit_2 ?? s.ai_signal.target_2)}</td>
                  <td>{(td?.risk_reward_ratio ?? s.ai_signal.risk_reward_ratio).toFixed(2)}</td>
                  <td className="muted">{td?.expected_holding_time ?? "—"}</td>
                  <td className="reason-cell muted">{reason.slice(0, 80)}{reason.length > 80 ? "…" : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
