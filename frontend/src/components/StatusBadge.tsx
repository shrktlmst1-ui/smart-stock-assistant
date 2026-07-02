import type { StockStatus } from "../types";

const STATUS_CLASS: Record<StockStatus, string> = {
  شراء: "status-buy",
  انتظار: "status-wait",
  خطر: "status-danger",
  خروج: "status-exit",
};

export function StatusBadge({ status }: { status: StockStatus }) {
  return <span className={`badge ${STATUS_CLASS[status]}`}>{status}</span>;
}

export function formatVolume(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

export function formatPrice(p: number): string {
  return p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
