function Indicator({ name, status }) {
  const cfg = {
    healthy:  { color: "#22c55e", label: "Healthy" },
    degraded: { color: "#f59e0b", label: "Degraded" },
    down:     { color: "#ef4444", label: "Down" },
    unknown:  { color: "#6b7280", label: "Unknown" },
  }[status ?? "unknown"];

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 16px",
      background: "#1f2937", borderRadius: 8, border: `1px solid ${cfg.color}33` }}>
      <div style={{ width: 10, height: 10, borderRadius: "50%", background: cfg.color,
        boxShadow: `0 0 6px ${cfg.color}` }} />
      <div>
        <div style={{ fontWeight: 600, fontSize: 13 }}>{name}</div>
        <div style={{ fontSize: 11, color: cfg.color }}>{cfg.label}</div>
      </div>
    </div>
  );
}

export default function SystemHealth({ health }) {
  return (
    <div style={{ display: "flex", gap: 12 }}>
      <Indicator name="Restaurant" status={health?.restaurant} />
      <Indicator name="Courier"    status={health?.courier} />
    </div>
  );
}
