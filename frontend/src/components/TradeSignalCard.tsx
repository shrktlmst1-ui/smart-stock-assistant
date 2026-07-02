import type { TradeDecision } from "../types";
import { formatPrice } from "./StatusBadge";

const SIGNAL_CLASS: Record<string, string> = {
  BUY: "ai-strong-buy",
  SELL: "ai-strong-sell",
  WAIT: "ai-wait",
  AVOID: "ai-strong-sell",
  "NO TRADE": "ai-wait",
  WATCH: "ai-wait",
  "POSSIBLE ENTRY": "ai-buy",
  "ENTRY CONFIRMED": "ai-strong-buy",
  "AVOID / TRAP RISK": "ai-strong-sell",
};

export function TradeSignalCard({ decision }: { decision: TradeDecision | null }) {
  if (!decision) return null;

  const signal = decision.professional_signal ?? decision.recommendation;
  const cls = SIGNAL_CLASS[signal] ?? "ai-wait";

  return (
    <div className={`card ai-signal-card ${cls}`}>
      <div className="ai-signal-header">
        <span className={`ai-badge ${cls}`}>{signal}</span>
        <span className="ai-confidence">
          {decision.symbol} · ${formatPrice(decision.current_price)} · AI {(decision.professional_ai_score ?? decision.ai_confidence).toFixed(0)}
        </span>
      </div>

      <div className="ai-levels">
        <div>
          <span className="muted">Entry Zone</span>
          <strong>
            ${formatPrice(decision.entry_zone_low)} – ${formatPrice(decision.entry_zone_high)}
          </strong>
        </div>
        <div>
          <span className="muted">Stop Loss</span>
          <strong>${formatPrice(decision.stop_loss)}</strong>
        </div>
        <div>
          <span className="muted">TP1</span>
          <strong>${formatPrice(decision.take_profit_1)}</strong>
        </div>
        <div>
          <span className="muted">TP2</span>
          <strong>${formatPrice(decision.take_profit_2)}</strong>
        </div>
        <div>
          <span className="muted">R:R</span>
          <strong>{decision.risk_reward_ratio.toFixed(2)}</strong>
        </div>
        <div>
          <span className="muted">Liquidity In</span>
          <strong>{decision.liquidity_inflow.toFixed(0)}%</strong>
        </div>
        <div>
          <span className="muted">Liquidity Out</span>
          <strong>{decision.liquidity_outflow.toFixed(0)}%</strong>
        </div>
        <div>
          <span className="muted">Trap Risk</span>
          <strong>{decision.trap_risk.toFixed(0)}%</strong>
        </div>
        <div>
          <span className="muted">News Risk</span>
          <strong>{decision.news_risk.toFixed(0)}%</strong>
        </div>
        <div>
          <span className="muted">Holding Time</span>
          <strong>{decision.expected_holding_time || "—"}</strong>
        </div>
        <div>
          <span className="muted">18-Factor Gate</span>
          <strong>{decision.all_filters_passed ? "PASS" : "FAIL"}</strong>
        </div>
      </div>

      <div className="signals-section">
        <p><span className="muted">AI Explanation: </span>{decision.ai_explanation || decision.trigger_reason}</p>
        <p><span className="muted">Structure: </span>{decision.market_structure}</p>
        <p><span className="muted">Devil&apos;s Advocate: </span>{decision.devils_advocate}</p>
      </div>

      {decision.engine_logs && decision.engine_logs.length > 0 && (
        <details className="engine-logs">
          <summary>Engine Logs ({decision.engine_logs.length})</summary>
          <ul>
            {decision.engine_logs.map((log, i) => (
              <li key={i}>
                <strong>{log.engine}</strong>: {log.result} — {log.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
