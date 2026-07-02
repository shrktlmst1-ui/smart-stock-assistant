import { useState } from "react";
import { ScannerPanel, TopOpportunitiesPanel } from "./components/ScannerPanel";
import { TradeSignalCard } from "./components/TradeSignalCard";
import { AlertsPanel } from "./components/AlertsPanel";
import { ConnectionPanel } from "./components/ConnectionPanel";
import { MetersPanel } from "./components/MetersPanel";
import { PerformancePanel } from "./components/PerformancePanel";
import { StockDetail } from "./components/StockDetail";
import { StockTable } from "./components/StockTable";
import { useMarketData } from "./hooks/useMarketData";
import "./App.css";

export default function App() {
  const { stockList, allAlerts, connected, lastUpdate, connectionStatus, aggregateMeters, lastNotification, performance, scanState } =
    useMarketData();
  const [selected, setSelected] = useState<string | null>(null);

  const selectedStock = stockList.find((s) => s.symbol === selected) ?? stockList[0] ?? null;

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Smart Stock Assistant</h1>
          <p className="subtitle">Phase 3 — Institutional AI Scanner · Top 20 · 15s refresh</p>
        </div>
        <div className="header-status">
          <span className={`dot ${connected ? "online" : "offline"}`} />
          {connected ? "متصل لحظياً" : "إعادة الاتصال..."}
          {lastUpdate && <small>آخر تحديث: {new Date(lastUpdate).toLocaleTimeString("ar")}</small>}
          {lastNotification && (
            <small className="last-notif">
              آخر تنبيه: {lastNotification.symbol} — {lastNotification.signal}
            </small>
          )}
        </div>
      </header>

      <main className="dashboard">
        <section className="main-col">
          <ConnectionPanel status={connectionStatus} />
          <MetersPanel meters={selectedStock?.meters ?? aggregateMeters} />
          <PerformancePanel metrics={performance} />
          <ScannerPanel state={scanState} />
          <TopOpportunitiesPanel state={scanState} />
          <StockTable stocks={stockList} selected={selectedStock?.symbol ?? null} onSelect={setSelected} scanState={scanState} />
          <AlertsPanel alerts={allAlerts} />
        </section>
        <aside className="side-col">
          <TradeSignalCard decision={selectedStock?.trade_decision ?? null} />
          <StockDetail stock={selectedStock} />
        </aside>
      </main>

      <footer className="footer">
        ⚠️ للمتابعة والتحليل فقط — لا ينفذ شراء أو بيع تلقائياً. ليست نصيحة استثمارية.
      </footer>
    </div>
  );
}
