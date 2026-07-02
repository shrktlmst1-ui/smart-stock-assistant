import type { AISignal, AISignalType } from "../types";
import { formatPrice } from "./StatusBadge";

const SIGNAL_CLASS: Record<AISignalType, string> = {
  "Strong Buy": "ai-strong-buy",
  Buy: "ai-buy",
  Wait: "ai-wait",
  Sell: "ai-sell",
  "Strong Sell": "ai-strong-sell",
};

export function AISignalCard({ signal }: { signal: AISignal | null }) {
  if (!signal) return null;

  return (
    <div className={`card ai-signal-card ${SIGNAL_CLASS[signal.signal]}`}>
      <div className="ai-signal-header">
        <span className={`ai-badge ${SIGNAL_CLASS[signal.signal]}`}>{signal.signal}</span>
        <span className="ai-confidence">
          {signal.confidence.toFixed(0)}% confidence · AI {signal.ai_score.toFixed(0)}
        </span>
      </div>
      {signal.confidence_breakdown && (
        <div className="ai-confidence-breakdown">
          <span className="muted">Confidence factors: </span>
          T{signal.confidence_breakdown.trend.toFixed(0)} V{signal.confidence_breakdown.volume.toFixed(0)}{" "}
          SMC{signal.confidence_breakdown.smc.toFixed(0)} L{signal.confidence_breakdown.liquidity.toFixed(0)}{" "}
          Vol{signal.confidence_breakdown.volatility.toFixed(0)} N{signal.confidence_breakdown.news.toFixed(0)}
        </div>
      )}
      <div className="ai-levels">
        <div><span className="muted">Entry</span><strong>${formatPrice(signal.entry)}</strong></div>
        <div><span className="muted">Stop Loss</span><strong>${formatPrice(signal.stop_loss)}</strong></div>
        <div><span className="muted">Target 1</span><strong>${formatPrice(signal.target_1)}</strong></div>
        <div><span className="muted">Target 2</span><strong>${formatPrice(signal.target_2)}</strong></div>
        <div><span className="muted">R:R</span><strong>{signal.risk_reward_ratio.toFixed(2)}</strong></div>
        <div><span className="muted">Risk</span><strong>{signal.risk_level}</strong></div>
      </div>
    </div>
  );
}
