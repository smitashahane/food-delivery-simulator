import { useState, useEffect, useRef, useCallback } from "react";

async function fetchConfig() {
  const r = await fetch("/api/chaos/config");
  return r.json();
}

async function post(path, body) {
  await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── Shared controls ───────────────────────────────────────────────────────────

function SliderRow({ label, value, min, max, step = 0.05, format, onChange }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 12, color: "#6b7280" }}>{label}</span>
        <span style={{ fontSize: 12, color: "#111827", fontWeight: 600 }}>{format(value)}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        style={{ width: "100%", accentColor: "#6366f1", cursor: "pointer" }} />
    </div>
  );
}

function Toggle({ label, checked, onChange, color = "#ef4444" }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
      <span style={{ fontSize: 12, color: "#6b7280" }}>{label}</span>
      <div onClick={() => onChange(!checked)} style={{
        width: 40, height: 22, borderRadius: 11, cursor: "pointer",
        background: checked ? color : "#d1d5db", position: "relative", transition: "background 0.2s",
      }}>
        <div style={{
          position: "absolute", top: 3, left: checked ? 21 : 3,
          width: 16, height: 16, borderRadius: "50%", background: "#fff", transition: "left 0.2s",
        }} />
      </div>
    </div>
  );
}

// ── Service panel ─────────────────────────────────────────────────────────────

function ServicePanel({ label, config, failurePath, latencyPath, blackoutPath, autoBlackoutPath, color }) {
  const [failureRate,  setFailureRate]  = useState(0.2);
  const [latencyMax,   setLatencyMax]   = useState(8);
  const [blackout,     setBlackout]     = useState(false);
  const [autoBlackout, setAutoBlackout] = useState(false);

  // Sync sliders when live config arrives
  useEffect(() => {
    if (!config) return;
    setFailureRate(config.failure_rate ?? 0.2);
    setLatencyMax(config.latency_max ?? 8);
    setBlackout(config.blackout ?? false);
    if (config.auto_blackout !== undefined) setAutoBlackout(config.auto_blackout);
  }, [config]);

  const debounce = useRef({});
  const send = useCallback((path, body, key) => {
    clearTimeout(debounce.current[key]);
    debounce.current[key] = setTimeout(() => post(path, body), 300);
  }, []);

  const statusColor = blackout ? "#ef4444" : failureRate > 0.5 ? "#f59e0b" : "#22c55e";
  const statusLabel = blackout ? "DOWN" : failureRate > 0.5 ? "DEGRADED" : "HEALTHY";

  return (
    <div style={{ flex: 1, background: "#ffffff", border: `1px solid ${color}`, borderRadius: 8, padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <span style={{ fontWeight: 700, color, fontSize: 14 }}>{label}</span>
        <span style={{
          fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 4,
          background: statusColor + "22", color: statusColor, border: `1px solid ${statusColor}`,
        }}>{statusLabel}</span>
      </div>

      <Toggle label="Blackout (total outage)" checked={blackout} onChange={v => {
        setBlackout(v);
        post(blackoutPath, { enabled: v });
      }} />

      {autoBlackoutPath && (
        <Toggle label="Random auto-blackout" checked={autoBlackout} onChange={v => {
          setAutoBlackout(v);
          post(autoBlackoutPath, { enabled: v });
        }} color="#f59e0b" />
      )}

      <SliderRow label="Failure rate" value={failureRate} min={0} max={1} step={0.05}
        format={v => `${Math.round(v * 100)}%`}
        onChange={v => { setFailureRate(v); send(failurePath, { rate: v }, "failure"); }} />

      <SliderRow label="Max latency" value={latencyMax} min={0.5} max={30} step={0.5}
        format={v => `${v.toFixed(1)}s`}
        onChange={v => { setLatencyMax(v); send(latencyPath, { min_s: 1, max_s: v }, "latency"); }} />
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ChaosControls() {
  const [config,      setConfig]      = useState(null);
  const [burstActive, setBurstActive] = useState(false);
  const [burstRemain, setBurstRemain] = useState(0);
  const [burstRps,    setBurstRps]    = useState(50);
  const [burstDur,    setBurstDur]    = useState(60);

  useEffect(() => {
    fetchConfig().then(setConfig).catch(() => {});
  }, []);

  useEffect(() => {
    const id = setInterval(() => {
      fetch("/api/chaos/loadgen/status")
        .then(r => r.json())
        .then(d => { setBurstActive(d.burst_active); setBurstRemain(d.remaining_s ?? 0); })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(id);
  }, []);

  const triggerBurst = () =>
    post("/api/chaos/loadgen/burst", { duration: burstDur, burst_rps: burstRps })
      .then(() => { setBurstActive(true); setBurstRemain(burstDur); });

  const stopBurst = () =>
    post("/api/chaos/loadgen/stop", {})
      .then(() => { setBurstActive(false); setBurstRemain(0); });

  return (
    <div>
      <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
        <ServicePanel
          label="Restaurant Simulator"
          config={config?.restaurant}
          failurePath="/api/chaos/restaurant/failure-rate"
          latencyPath="/api/chaos/restaurant/latency"
          blackoutPath="/api/chaos/restaurant/blackout"
          color="#f97316"
        />
        <ServicePanel
          label="Courier Simulator"
          config={config?.courier}
          failurePath="/api/chaos/courier/failure-rate"
          latencyPath="/api/chaos/courier/latency"
          blackoutPath="/api/chaos/courier/blackout"
          autoBlackoutPath="/api/chaos/courier/auto-blackout"
          color="#8b5cf6"
        />
      </div>

      {/* Dinner Rush */}
      <div style={{ background: "#ffffff", border: "1px solid #f59e0b", borderRadius: 8, padding: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
          <span style={{ fontWeight: 700, color: "#f59e0b", fontSize: 14 }}>Dinner Rush</span>
          <span style={{ fontSize: 11, color: "#6b7280" }}>requires <code style={{ color: "#6b7280" }}>make loadgen</code></span>
        </div>

        <div style={{ display: "flex", gap: 16, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 160 }}>
            <SliderRow label="Burst rate (orders/sec)" value={burstRps} min={10} max={200} step={10}
              format={v => `${v}/s`} onChange={setBurstRps} />
            <SliderRow label="Duration" value={burstDur} min={15} max={300} step={15}
              format={v => `${v}s`} onChange={setBurstDur} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            {burstActive ? (
              <>
                <div style={{ fontSize: 12, color: "#f59e0b", fontWeight: 700 }}>
                  ACTIVE — {burstRemain}s left · {burstRps}/s
                </div>
                <button onClick={stopBurst} style={{
                  padding: "10px 28px", background: "#ef4444", color: "#fff",
                  border: "none", borderRadius: 6, fontWeight: 700, fontSize: 14, cursor: "pointer",
                }}>Stop Rush</button>
              </>
            ) : (
              <button onClick={triggerBurst} style={{
                padding: "10px 28px", background: "#f59e0b", color: "#ffffff",
                border: "none", borderRadius: 6, fontWeight: 700, fontSize: 14, cursor: "pointer",
              }}>Trigger Dinner Rush</button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
