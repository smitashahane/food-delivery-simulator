const STATUS_META = {
  placed:           { label: "Placed",           color: "#6366f1" },
  confirmed:        { label: "Confirmed",         color: "#3b82f6" },
  preparing:        { label: "Preparing",         color: "#f59e0b" },
  ready:            { label: "Ready",             color: "#10b981" },
  out_for_delivery: { label: "Out for Delivery",  color: "#8b5cf6" },
  delivered:        { label: "Delivered",         color: "#22c55e" },
  failed:           { label: "Failed",            color: "#ef4444" },
  cancelled:        { label: "Cancelled",         color: "#6b7280" },
  dead_lettered:    { label: "Dead Lettered",     color: "#dc2626" },
};

export default function StatusCounts({ counts }) {
  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
      {Object.entries(STATUS_META).map(([key, { label, color }]) => (
        <div key={key} style={{
          background: "#1f2937",
          border: `1px solid ${color}`,
          borderRadius: 8,
          padding: "12px 20px",
          minWidth: 110,
          textAlign: "center",
        }}>
          <div style={{ fontSize: 28, fontWeight: 700, color }}>{counts?.[key] ?? 0}</div>
          <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>{label}</div>
        </div>
      ))}
    </div>
  );
}
