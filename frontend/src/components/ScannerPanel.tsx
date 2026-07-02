import type { MarketScanState } from "../types";
import { formatPrice } from "./StatusBadge";

export function ScannerPanel({ state }: { state: MarketScanState | null }) {
  if (!state) return null;

  return (
    <div className="card scanner-panel">
      <div className="card-header">
        <h2>US Market Scanner</h2>
        <span className="muted">
          {state.liquid_count.toLocaleString()} liquid / {state.universe_size.toLocaleString()} tickers · {state.last_tick_ms.toFixed(0)}ms
        </span>
      </div>
      <div className="scanner-boards">
        {state.boards.map((board) => (
          <div key={board.board_type} className="scanner-board">
            <h3>{board.title}</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Price</th>
                    <th>Chg%</th>
                    <th>RVOL</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {board.rows.slice(0, 8).map((r) => (
                    <tr key={`${board.board_type}-${r.symbol}`}>
                      <td><strong>{r.symbol}</strong></td>
                      <td>${formatPrice(r.price)}</td>
                      <td className={r.change_percent >= 0 ? "up" : "down"}>
                        {r.change_percent >= 0 ? "+" : ""}{r.change_percent.toFixed(2)}%
                      </td>
                      <td>{r.relative_volume.toFixed(1)}x</td>
                      <td className="muted">{r.scanner_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TopOpportunitiesPanel({ state }: { state: MarketScanState | null }) {
  if (!state?.top_opportunities?.length) return null;

  return (
    <div className="card">
      <div className="card-header">
        <h2>Institutional Top 20</h2>
        <span className="muted">All 18 factors passed · ranked by AI Score</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>AI</th>
              <th>Decision</th>
              <th>Hold</th>
              <th>Conf</th>
              <th>R:R</th>
              <th>Trap</th>
              <th>Liq</th>
              <th>News</th>
            </tr>
          </thead>
          <tbody>
            {state.top_opportunities.map((s) => (
              <tr key={s.symbol}>
                <td><strong>{s.symbol}</strong><small>{s.name}</small></td>
                <td>{s.ai_score.toFixed(0)}</td>
                <td>{s.recommendation}</td>
                <td className="muted">{s.expected_holding_time ?? "—"}</td>
                <td>{s.confidence.toFixed(0)}%</td>
                <td>{s.risk_reward_ratio.toFixed(1)}</td>
                <td>{s.trap_risk.toFixed(0)}%</td>
                <td>{s.liquidity_score.toFixed(0)}</td>
                <td>{s.news_risk.toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
