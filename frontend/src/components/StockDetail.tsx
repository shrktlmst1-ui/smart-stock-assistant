import type { StockSnapshot } from "../types";
import { StatusBadge, formatPrice } from "./StatusBadge";

interface Props {
  stock: StockSnapshot | null;
}

export function StockDetail({ stock }: Props) {
  if (!stock) {
    return (
      <div className="card detail-card empty-detail">
        <p>اختر سهماً من القائمة لعرض التفاصيل</p>
      </div>
    );
  }

  const { indicators: ind, signals: sig } = stock;

  return (
    <div className="card detail-card">
      <div className="detail-header">
        <div>
          <h2>{stock.symbol}</h2>
          <p className="muted">{stock.name}</p>
        </div>
        <StatusBadge status={stock.status} />
      </div>

      <div className="price-row">
        <span className="big-price">${formatPrice(stock.price)}</span>
        <span className={stock.change_percent >= 0 ? "up" : "down"}>
          {stock.change_percent >= 0 ? "+" : ""}
          {stock.change_percent.toFixed(2)}%
        </span>
      </div>

      <div className="grid-2">
        <Metric label="RSI" value={ind.rsi.toFixed(1)} />
        <Metric label="MACD" value={ind.macd.toFixed(3)} />
        <Metric label="VWAP" value={`$${ind.vwap}`} />
        <Metric label="EMA 9" value={`$${ind.ema_9}`} />
        <Metric label="EMA 20" value={`$${ind.ema_20}`} />
        <Metric label="EMA 50" value={`$${ind.ema_50}`} />
        <Metric label="EMA 200" value={`$${ind.ema_200}`} />
        <Metric label="الدعم" value={`$${ind.support}`} />
        <Metric label="المقاومة" value={`$${ind.resistance}`} />
        <Metric label="ضغط شراء" value={`${sig.buy_pressure}%`} />
        <Metric label="ضغط بيع" value={`${sig.sell_pressure}%`} />
      </div>

      <div className="signals-section">
        <h3>SMC — Smart Money Concepts</h3>
        <p>{stock.smc.summary}</p>
        <div className="signal-tags">
          {stock.smc.mss && <Tag label={`MSS ${stock.smc.mss_direction}`} />}
          {stock.smc.bos && <Tag label={`BOS ${stock.smc.bos_direction}`} />}
          {stock.smc.choch && <Tag label={`CHOCH ${stock.smc.choch_direction}`} />}
          {stock.smc.liquidity_sweep && <Tag label="Liquidity Sweep" />}
          {stock.smc.order_blocks?.length > 0 && (
            <Tag label={`OB ${stock.smc.order_blocks[stock.smc.order_blocks.length - 1].type}`} />
          )}
          {stock.smc.fair_value_gaps?.length > 0 && (
            <Tag label={`FVG ${stock.smc.fair_value_gaps[stock.smc.fair_value_gaps.length - 1].type}`} />
          )}
        </div>
      </div>

      {stock.market_regime && (
      <div className="signals-section">
        <h3>Market Regime</h3>
        <p>{stock.market_regime.summary}</p>
        <div className="grid-2">
          <Metric label="Regime" value={stock.market_regime.regime} />
          <Metric label="Score" value={`${stock.market_regime.score.toFixed(0)}%`} />
          <Metric label="Volatility" value={stock.market_regime.volatility_regime} />
          <Metric label="Trend Quality" value={`${stock.market_regime.trend_quality.toFixed(0)}%`} />
        </div>
      </div>
      )}

      {stock.smart_money && (
      <div className="signals-section">
        <h3>Smart Money Tracker</h3>
        <p>{stock.smart_money.summary}</p>
        <div className="signal-tags">
          {stock.smart_money.whale_order && <Tag label="Whale Order" />}
          {stock.smart_money.hidden_accumulation && <Tag label="Hidden Accumulation" />}
          {stock.smart_money.hidden_distribution && <Tag label="Hidden Distribution" danger />}
          {stock.smart_money.absorption && <Tag label="Absorption" />}
          {stock.smart_money.iceberg_activity && <Tag label="Iceberg Activity" />}
          <Tag label={`Flow ${stock.smart_money.flow_direction}`} />
        </div>
      </div>
      )}

      {stock.liquidity_traps && (
      <div className="signals-section">
        <h3>Liquidity Trap Detector</h3>
        <p>{stock.liquidity_traps.summary}</p>
        <div className="signal-tags">
          {stock.liquidity_traps.bull_trap && <Tag label="Bull Trap" danger />}
          {stock.liquidity_traps.bear_trap && <Tag label="Bear Trap" danger />}
          {stock.liquidity_traps.fake_breakout && <Tag label="Fake Breakout" danger />}
          {stock.liquidity_traps.stop_hunt && <Tag label="Stop Hunt" danger />}
          {stock.liquidity_traps.liquidity_grab && <Tag label="Liquidity Grab" />}
          {stock.liquidity_traps.severity > 0 && (
            <Tag label={`Severity ${stock.liquidity_traps.severity.toFixed(0)}%`} danger />
          )}
        </div>
      </div>
      )}

      {stock.risk_assessment && (
      <div className="signals-section">
        <h3>Risk Engine</h3>
        <p>{stock.risk_assessment.summary}</p>
        <div className="grid-2">
          <Metric label="Position Size" value={`${stock.risk_assessment.position_size_shares} shares`} />
          <Metric label="Position $" value={`$${stock.risk_assessment.position_size_dollars.toLocaleString()}`} />
          <Metric label="Risk %" value={`${stock.risk_assessment.risk_percent.toFixed(2)}%`} />
          <Metric label="Reward %" value={`${stock.risk_assessment.reward_percent.toFixed(2)}%`} />
          <Metric label="ATR Stop" value={`$${stock.risk_assessment.atr_stop}`} />
          <Metric label="Dynamic TP" value={`$${stock.risk_assessment.dynamic_take_profit}`} />
        </div>
      </div>
      )}

      <div className="signals-section">
        <h3>Trend Engine</h3>
        <p>{stock.trend_analysis.summary}</p>
        <div className="grid-2">
          <Metric label="ATR" value={stock.trend_analysis.atr.toFixed(2)} />
          <Metric label="Trend" value={`${stock.trend_analysis.direction} (${stock.trend_analysis.trend_strength.toFixed(0)}%)`} />
          <Metric label="VWAP" value={`$${stock.trend_analysis.vwap.toFixed(2)}`} />
          <Metric label="EMA Stack" value={
            stock.trend_analysis.ema_stack_bullish ? "Bullish" :
            stock.trend_analysis.ema_stack_bearish ? "Bearish" : "Mixed"
          } />
        </div>
      </div>

      <div className="signals-section">
        <h3>Liquidity & Volume</h3>
        <p>{stock.liquidity_engine.summary} | {stock.volume_engine.summary}</p>
        <div className="signal-tags">
          {stock.liquidity_engine.liquidity_grab && <Tag label="Liquidity Grab" />}
          {stock.liquidity_engine.liquidity_trap && <Tag label="Liquidity Trap" danger />}
          {stock.volume_engine.volume_spike && <Tag label="Volume Spike" />}
          {stock.volume_engine.unusual_volume && <Tag label="Unusual Volume" />}
          {stock.volume_engine.volume_divergence && (
            <Tag label={`Divergence ${stock.volume_engine.divergence_direction}`} />
          )}
          {stock.volume_engine.dark_pool_estimate > 40 && (
            <Tag label={`Dark Pool ~${stock.volume_engine.dark_pool_estimate.toFixed(0)}%`} />
          )}
        </div>
      </div>

      {stock.news_intelligence.items.length > 0 && (
        <div className="news-section">
          <h3>News Intelligence ({stock.news_intelligence.source})</h3>
          <p className="muted">
            Sentiment: {stock.news_intelligence.overall_sentiment} |
            Impact: {stock.news_intelligence.confidence_adjustment > 0 ? "+" : ""}
            {stock.news_intelligence.confidence_adjustment}%
          </p>
          {stock.news_intelligence.items.slice(0, 3).map((n, i) => (
            <div key={i} className="news-item">
              <span className={`sentiment-${n.sentiment}`}>[{n.sentiment}]</span> {n.headline}
            </div>
          ))}
        </div>
      )}

      <div className="signals-section">
        <h3>تحليل الإشارات</h3>
        <p>{sig.summary || "لا إشارات قوية"}</p>
        <div className="signal-tags">
          {sig.liquidity_inflow && <Tag label="دخول سيولة" />}
          {sig.liquidity_outflow && <Tag label="خروج سيولة" danger />}
          {sig.smart_money_inflow && <Tag label="أموال ذكية" />}
          {sig.smart_money_outflow && <Tag label="خروج أموال ذكية" danger />}
          {sig.order_flow_bullish && <Tag label="تدفق شراء" />}
          {sig.order_flow_bearish && <Tag label="تدفق بيع" danger />}
          {sig.volume_spike && <Tag label="قفزة فوليوم" />}
          {sig.true_breakout && <Tag label="اختراق حقيقي" />}
          {sig.false_breakout && <Tag label="اختراق وهمي" danger />}
          {sig.abnormal_volume && <Tag label="فوليوم غير طبيعي" />}
          {sig.large_buy_volume && <Tag label="شراء كبير" />}
          {sig.market_trap && <Tag label="فخ سوق" danger />}
          {sig.fake_pump && <Tag label="ضخ وهمي" danger />}
          {sig.liquidity_trap && <Tag label="مصيدة سيولة" danger />}
        </div>
      </div>

      {stock.alerts.length > 0 && (
        <div className="reason-section">
          <h3>سبب التنبيه</h3>
          {stock.alerts.map((a, i) => (
            <div key={i} className="reason-item">
              <strong>{a.title}:</strong> {a.message}
            </div>
          ))}
        </div>
      )}

      {stock.news.length > 0 && (
        <div className="news-section">
          <h3>آخر الأخبار</h3>
          {stock.news.map((n) => (
            <div key={n.id} className="news-item">
              {n.url ? (
                <a href={n.url} target="_blank" rel="noreferrer">
                  {n.title}
                </a>
              ) : (
                <span>{n.title}</span>
              )}
              <small>
                {n.source} — {n.published_at}
              </small>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span className="muted">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Tag({ label, danger }: { label: string; danger?: boolean }) {
  return <span className={`tag ${danger ? "tag-danger" : ""}`}>{label}</span>;
}
