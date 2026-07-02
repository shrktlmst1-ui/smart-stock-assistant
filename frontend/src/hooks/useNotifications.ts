import { useEffect } from "react";
import type { NotificationPayload } from "../types";

export function useNotifications(onNotify?: (n: NotificationPayload) => void) {
  useEffect(() => {
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  const handleNotification = (payload: NotificationPayload) => {
    if (payload.confidence < 85) return;
    if (payload.signal === "Wait") return;

    if (payload.desktop && typeof Notification !== "undefined" && Notification.permission === "granted") {
      new Notification(`${payload.symbol} — ${payload.signal}`, {
        body: `${payload.confidence}% | ${payload.reason}`,
        icon: "/favicon.ico",
      });
    }
    if (payload.sound) {
      try {
        const ctx = new AudioContext();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = payload.signal.includes("Buy") ? 880 : 440;
        gain.gain.value = 0.08;
        osc.start();
        osc.stop(ctx.currentTime + 0.15);
      } catch {
        /* audio not available */
      }
    }
    onNotify?.(payload);
  };

  return { handleNotification };
}
