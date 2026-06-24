import { useState, useEffect } from "react";
import { useSSE } from "./hooks/useSSE";
import { fetchStats, fetchRecentOrders } from "./api";
import StatusCounts from "./components/StatusCounts";
import OrderFeed from "./components/OrderFeed";
import ThroughputChart from "./components/ThroughputChart";
import SystemHealth from "./components/SystemHealth";
import ChaosControls from "./components/ChaosControls";
import ApiExplorer from "./components/ApiExplorer";

const SECTION = {
  background: "#f9fafb", borderRadius: 10, padding: 20,
  border: "1px solid #e5e7eb", marginBottom: 16,
};
const HEADING = { fontSize: 13, fontWeight: 600, color: "#6b7280", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 };

export default function App() {
  const [stats, setStats]       = useState(null);
  const [orders, setOrders]     = useState([]);
  const [history, setHistory]   = useState([]);
  const sseEvents               = useSSE("/stream");

  // Poll /api/stats every 10 s
  useEffect(() => {
    async function load() {
      try {
        const s = await fetchStats();
        setStats(s);
        // Use server-side throughput history buckets when available
        if (s.throughput_history?.length) {
          setHistory(s.throughput_history);
        } else {
          const t = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
          setHistory((h) => [...h, { t, opm: s.orders_per_minute_last_5 }].slice(-30));
        }
      } catch (_) {}
    }
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  // Reload order list when SSE fires a new event
  useEffect(() => {
    if (!sseEvents.length) return;
    fetchRecentOrders(50).then((r) => setOrders(r.orders)).catch(() => {});
  }, [sseEvents]);

  // Initial order load
  useEffect(() => {
    fetchRecentOrders(50).then((r) => setOrders(r.orders)).catch(() => {});
  }, []);

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: 24 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>Food Delivery Pipeline</h1>
          <p style={{ color: "#4b5563", fontSize: 13, marginTop: 2 }}>Live operations view</p>
        </div>
        <span style={{ color: "#6b7280", fontSize: 12 }}>
          {stats ? `${stats.orders_per_minute_last_5} orders/min` : "connecting…"}
        </span>
      </div>

      {/* API Explorer */}
      <div style={SECTION}>
        <div style={HEADING}>API Explorer</div>
        <ApiExplorer onOrderPlaced={() => fetchRecentOrders(50).then(r => setOrders(r.orders)).catch(() => {})} />
      </div>

      {/* System Health */}
      <div style={SECTION}>
        <div style={HEADING}>System Health</div>
        <SystemHealth health={stats?.downstream_health} />
      </div>

      {/* Status Counts */}
      <div style={SECTION}>
        <div style={HEADING}>Orders by Status</div>
        <StatusCounts counts={stats?.counts_by_status} />
      </div>

      {/* Throughput */}
      <div style={SECTION}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
          <div style={HEADING}>Throughput (orders/min)</div>
          <span style={{ color: "#6b7280", fontSize: 12 }}>
            Error rate: {stats ? (stats.error_rate_last_5min * 100).toFixed(1) + "%" : "—"}
          </span>
        </div>
        <ThroughputChart history={history} />
      </div>

      {/* Chaos Controls */}
      <div style={SECTION}>
        <div style={HEADING}>Chaos Controls</div>
        <ChaosControls />
      </div>

      {/* Order Feed */}
      <div style={SECTION}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
          <div style={HEADING}>Recent Orders</div>
          <span style={{ color: "#6b7280", fontSize: 12 }}>
            {sseEvents.length > 0 ? `${sseEvents.length} live events received` : "waiting for events…"}
          </span>
        </div>
        <OrderFeed orders={orders} />
      </div>
    </div>
  );
}
