import { useCallback, useEffect, useRef, useState } from "react";
import { useNotifications } from "./useNotifications";
import type { Alert, ConnectionStatus, MarketScanState, NotificationPayload, PerformanceMetrics, StockSnapshot, WsMessage } from "../types";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

function normalizeSnapshot(raw: StockSnapshot): StockSnapshot {
  return {
    ...raw,
    alerts: raw.alerts ?? [],
    smc: {
      ...raw.smc,
      order_blocks: raw.smc?.order_blocks ?? [],
      fair_value_gaps: raw.smc?.fair_value_gaps ?? [],
    },
    meters: {
      smart_money_meter: raw.meters?.smart_money_meter ?? 50,
      liquidity_meter: raw.meters?.liquidity_meter ?? 50,
      trend_strength: raw.meters?.trend_strength ?? 50,
      market_risk: raw.meters?.market_risk ?? 50,
      institutional_activity: raw.meters?.institutional_activity ?? 50,
      ai_confidence: raw.meters?.ai_confidence ?? 50,
      fear_greed: raw.meters?.fear_greed,
    },
    trade_decision: raw.trade_decision ?? {
      recommendation: "WAIT",
      direction: "neutral",
      symbol: raw.symbol,
      current_price: raw.price,
      entry_zone_low: 0,
      entry_zone_high: 0,
      stop_loss: 0,
      take_profit_1: 0,
      take_profit_2: 0,
      risk_reward_ratio: 0,
      ai_confidence: raw.meters?.ai_confidence ?? 50,
      liquidity_inflow: 50,
      liquidity_outflow: 50,
      trap_risk: 0,
      news_risk: 0,
      market_structure: "",
      trigger_reason: "",
      devils_advocate: "",
      engine_logs: [],
    },
    volume_liquidity: raw.volume_liquidity ?? {
      relative_volume: 1,
      volume_spike: false,
      cumulative_delta: 0,
      delta_direction: "neutral",
      vwap: raw.indicators?.vwap ?? 0,
      price_vs_vwap: "at",
      premarket_volume: 0,
      premarket_rvol: 1,
      gap_percent: 0,
      gap_type: "none",
      liquidity_inflow: 50,
      liquidity_outflow: 50,
      buyer_pressure: raw.signals?.buy_pressure ?? 50,
      seller_pressure: raw.signals?.sell_pressure ?? 50,
      summary: "",
    },
    news_risk: raw.news_risk ?? {
      risk_level: "low",
      risk_score: 0,
      block_trade: false,
      matched_events: [],
      summary: "",
    },
  };
}

export function useMarketData() {
  const [stocks, setStocks] = useState<Map<string, StockSnapshot>>(new Map());
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<string>("");
  const [performance, setPerformance] = useState<PerformanceMetrics | null>(null);
  const [scanState, setScanState] = useState<MarketScanState | null>(null);
  const [lastNotification, setLastNotification] = useState<NotificationPayload | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const { handleNotification } = useNotifications((n) => setLastNotification(n));

  const mergeSnapshot = useCallback((snap: StockSnapshot) => {
    const normalized = normalizeSnapshot(snap);
    setStocks((prev) => {
      const next = new Map(prev);
      next.set(normalized.symbol, normalized);
      return next;
    });
    setLastUpdate(normalized.last_updated);
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/status`)
      .then((r) => r.json())
      .then((data: ConnectionStatus) => setConnectionStatus(data))
      .catch(console.error);

    fetch(`${API_BASE}/stocks/dashboard`)
      .then((r) => r.json())
      .then((data: StockSnapshot[]) => data.forEach(mergeSnapshot))
      .catch(console.error);

    fetch(`${API_BASE}/performance`)
      .then((r) => r.json())
      .then((data: PerformanceMetrics) => setPerformance(data))
      .catch(console.error);
    fetch(`${API_BASE}/scanner/state`)
      .then((r) => r.json())
      .then((data: MarketScanState) => setScanState(data))
      .catch(console.error);
  }, [mergeSnapshot]);

  useEffect(() => {
    const perfTimer = setInterval(() => {
      fetch(`${API_BASE}/performance`)
        .then((r) => r.json())
        .then((data: PerformanceMetrics) => setPerformance(data))
        .catch(console.error);
    }, 10000);
    return () => clearInterval(perfTimer);
  }, []);

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let alive = true;

    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (alive) setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const msg: WsMessage = JSON.parse(event.data);
          if (msg.type === "snapshot") {
            mergeSnapshot(msg.data as StockSnapshot);
          }
          if (msg.type === "status") {
            setConnectionStatus(msg.data as ConnectionStatus);
          }
          if (msg.type === "scan_update") {
            setScanState(msg.data as MarketScanState);
            const state = msg.data as MarketScanState;
            if (state.top_opportunities?.length) {
              setStocks((prev) => {
                const next = new Map(prev);
                for (const snap of (state as MarketScanState & { snapshots?: StockSnapshot[] }).snapshots ?? []) {
                  if (snap?.symbol) next.set(snap.symbol, normalizeSnapshot(snap));
                }
                return next;
              });
            }
          }
          if (msg.type === "notification") {
            handleNotification(msg.data as NotificationPayload);
          }
          if (msg.timestamp) setLastUpdate(msg.timestamp);
        } catch {
          /* ignore */
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (alive) reconnectTimer = setTimeout(connect, 3000);
      };

      ws.onerror = () => ws.close();
    }

    connect();

    const ping = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send("ping");
      }
    }, 30000);

    return () => {
      alive = false;
      clearTimeout(reconnectTimer);
      clearInterval(ping);
      wsRef.current?.close();
    };
  }, [mergeSnapshot, handleNotification]);

  const stockList = Array.from(stocks.values()).sort(
    (a, b) => b.ai_signal.ai_score - a.ai_signal.ai_score,
  );

  const allAlerts = stockList
    .flatMap((s) => (s.alerts ?? []).map((a: Alert) => ({ ...a, symbol: s.symbol })))
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  const aggregateMeters = stockList.length
    ? {
        smart_money_meter: stockList.reduce((s, x) => s + x.meters.smart_money_meter, 0) / stockList.length,
        liquidity_meter: stockList.reduce((s, x) => s + x.meters.liquidity_meter, 0) / stockList.length,
        trend_strength: stockList.reduce((s, x) => s + x.meters.trend_strength, 0) / stockList.length,
        market_risk: stockList.reduce((s, x) => s + x.meters.market_risk, 0) / stockList.length,
        institutional_activity: stockList.reduce((s, x) => s + (x.meters.institutional_activity ?? 50), 0) / stockList.length,
        ai_confidence: stockList.reduce((s, x) => s + x.meters.ai_confidence, 0) / stockList.length,
      }
    : null;

  return { stockList, allAlerts, connected, lastUpdate, connectionStatus, aggregateMeters, lastNotification, performance, scanState };
}
