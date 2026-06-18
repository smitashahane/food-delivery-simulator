import { useState, useEffect, useRef, useCallback } from "react";

const BASE = "";

async function fetchConfig() {
  const r = await fetch(`${BASE}/api/chaos/config`);
  return r.json();
}

async function post(path, body) {
  await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SliderRow({ label, value, min, max, step = 0.05, format, onChange }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 12, color: "#9ca3af" }}>{label}</span>
        <span style={{ fontSize: 12, color: "#e5e7eb", fontWeight: 600 }}>{format(value)}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        style={{ width: "100%", accentColor: "#6366f1", cursor: "pointer" }}
      />
    </div>
  );
}

function Toggle({ label, checked, onChange, color = "#ef4444" }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
      <span style={{ fontSize: 12, color: "#9ca3af" }}>{label}</span>
      <div
        onClick={() => onChange(!checked)}
        style={{
          width: 40, height: 22, borderRadius: 11, cursor: "pointer",
          background: checked ? color : "#374151",
          position: "relative", transition: "background 0.2s",
        }}
      >
        <div style={{
          position: "absolute", top: 3, left: checked ? 21 : 3,
          width: 16, height: 16, borderRadius: "50%", background: "#fff",
          transition: "left 0.2s",
        }} />
      </div>
    </div>
  );
}

function ServicePanel({ name, label, config, failurePath, latencyPath, blackoutPath, color, initialLatencyMax }) {
  const [failureRate, setFailureRate] = useState(config?.failure_rate ?? 0.2);
  const [latencyMin,  setLatencyMin]  = useState(config?.latency_min  ?? 1);
  const [latencyMax,  setLatencyMax]  = useState(config?.latency_max  ?? initialLatencyMax ?? 8);
  const [blackout,    setBlackout]    = useState(config?.blackout      ?? false);

  const debounce = useRef({});

  const send = useCallback((path, body, key) => {
    clearTimeout(debounce.current[key]);
    debounce.current[key] = setTimeout(() => post(path, body), 300);
  }, []);

  const handleFailure = (v) => {
    setFailureRate(v);
    send(failurePath, { rate: v }, "failure");
  };
  const handleLatencyMin = (v) => {
    const safe = Math.min(v, latencyMax - 0.5);
    setLatencyMin(safe);
    send(latencyPath, { min_s: safe, max_s: latencyMax }, "latency");
  };
  const handleLatencyMax = (v) => {
    const safe = Math.max(v, latencyMin + 0.5);
    setLatencyMaxS(safe);
    send(latencyPath, { min_s: latencyMin, max_s: safe }, "latency");
  };
  const handleBlackout = (v) => {
    setBlackout(v);
    post(blackoutPath, { enabled: v });
  };

  const statusColor = blackout ? "#ef4444" : failureRate > 0.5 ? "#f59e0b" : "#22c55e";
  const statusLabel = blackout ? "DOWN" : failureRate > 0.5 ? "DEGRADED" : "HEALTHY";

  return (
    <div style={{
      flex: 1, background: "#111827", border: `1px solid ${color}33`,
      borderRadius: 8, padding: 16,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <span style={{ fontWeight: 700, color, fontSize: 14 }}>{label}</span>
        <span style={{
          fontSize: 10, fontWeight: 700, padding: "2px 8px",
          borderRadius: 4, background: statusColor + "22", color: statusColor,
          border: `1px solid ${statusColor}`,
        }}>{statusLabel}</span>
      </div>

      <Toggle
        label="Blackout (total outage)"
        checked={blackout}
        onChange={handleBlackout}
        color="#ef4444"
      />

      <SliderRow
        label="Failure rate"
        value={failureRate}
        min={0} max={1} step={0.05}
        format={v => `${Math.round(v * 100)}%`}
        onChange={handleFailure}
      />
      <SliderRow
        label="Latency min (s)"
        value={latencyMin}
        min={0} max={latencyMax - 0.5} step={0.5}
        format={v => `${v.toFixed(1)}s`}
        onChange={handleLatencyMin}
      />
      <SliderRow
        label="Latency max (s)"
        value={latencyMax}
        min={latencyMin + 0.5} max={30} step={0.5}
        format={v => `${v.toFixed(1)}s`}
        onChange={handleLatencyMax}
      />
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ChaosControls({ onBurstStart }) {
  const [config,       setConfig]       = useState(null);
  const [burstActive,  setBurstActive]  = useState(false);
  const [burstRemain,  setBurstRemain]  = useState(0);
  const [burstRps,     setBurstRps]     = useState(50);
  const [burstDur,     setBurstDur]     = useState(60);

  // Load initial config from simulators
  useEffect(() => {
    fetchConfig().then(setConfig).catch(() => {});
  }, []);

  // Poll burst status every 2s
  useEffect(() => {
    const id = setInterval(() => {
      fetch("/api/chaos/loadgen/status")
        .then(r => r.json())
        .then(d => {
          setBurstActive(d.burst_active);
          setBurstRemain(d.remaining_s ?? 0);
        })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(id);
  }, []);

  const triggerBurst = () => {
    post("/api/chaos/loadgen/burst", { duration: burstDur, burst_rps: burstRps })
      .then(() => {
        setBurstActive(true);
        setBurstRemain(burstDur);
        onBurstStart?.();
      });
  };

  return (
    <div>
      {/* Simulator panels */}
      <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
        <ServicePanel
          name="restaurant"
          label="Restaurant Simulator"
          config={config?.restaurant}
          failurePath="/api/chaos/restaurant/failure-rate"
          latencyPath="/api/chaos/restaurant/latency"
          blackoutPath="/api/chaos/restaurant/blackout"
          color="#f97316"
          initialLatencyMax={config?.restaurant?.latency_max ?? 8}
        />
        <ServicePanel
          name="courier"
          label="Courier Simulator"
          config={config?.courier}
          failurePath="/api/chaos/courier/failure-rate"
          latencyPath="/api/chaos/courier/latency"
          blackoutPath="/api/chaos/courier/blackout"
          color="#8b5cf6"
          initialLatencyMax={config?.courier?.latency_max ?? 3}
        />
      </div>

      {/* Dinner Rush */}
      <div style={{
        background: "#111827", border: "1px solid #f59e0b33",
        borderRadius: 8, padding: 16,
      }}>
        <div style={{ fontWeight: 700, color: "#f59e0b", fontSize: 14, marginBottom: 12 }}>
          Dinner Rush
        </div>

        <div style={{ display: "flex", gap: 16, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 160 }}>
            <SliderRow
              label="Burst rate (orders/sec)"
              value={burstRps}
              min={10} max={200} step={10}
              format={v => `${v}/s`}
              onChange={setBurstRps}
            />
            <SliderRow
              label="Duration (seconds)"
              value={burstDur}
              min={15} max={300} step={15}
              format={v => `${v}s`}
              onChange={setBurstDur}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <button
              onClick={triggerBurst}
              disabled={burstActive}
              style={{
                padding: "10px 28px",
                background: burstActive ? "#374151" : "#f59e0b",
                color: burstActive ? "#6b7280" : "#0f1117",
                border: "none", borderRadius: 6,
                fontWeight: 700, fontSize: 14, cursor: burstActive ? "not-allowed" : "pointer",
                transition: "background 0.2s",
              }}
            >
              {burstActive ? `RUSH ACTIVE — ${burstRemain}s left` : "Trigger Dinner Rush"}
            </button>
            {burstActive && (
              <span style={{ fontSize: 11, color: "#f59e0b" }}>
                {burstRps} orders/sec via loadgen
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
