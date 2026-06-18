const STATUS_COLOR = {
  placed: "#6366f1", confirmed: "#3b82f6", preparing: "#f59e0b",
  ready: "#10b981", out_for_delivery: "#8b5cf6", delivered: "#22c55e",
  failed: "#ef4444", cancelled: "#6b7280", dead_lettered: "#dc2626",
};

function Badge({ status }) {
  const color = STATUS_COLOR[status] ?? "#9ca3af";
  return (
    <span style={{
      background: color + "22", color, border: `1px solid ${color}`,
      borderRadius: 4, padding: "2px 8px", fontSize: 11, fontWeight: 600,
    }}>
      {status}
    </span>
  );
}

export default function OrderFeed({ orders }) {
  if (!orders?.length) {
    return <p style={{ color: "#6b7280", padding: 16 }}>No orders yet. Place one to get started.</p>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #374151", color: "#9ca3af" }}>
            <th style={{ textAlign: "left", padding: "8px 12px" }}>Order ID</th>
            <th style={{ textAlign: "left", padding: "8px 12px" }}>Restaurant</th>
            <th style={{ textAlign: "left", padding: "8px 12px" }}>Status</th>
            <th style={{ textAlign: "left", padding: "8px 12px" }}>Placed At</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.order_id} style={{ borderBottom: "1px solid #1f2937" }}>
              <td style={{ padding: "8px 12px", fontFamily: "monospace", color: "#d1d5db" }}>
                {o.order_id.slice(0, 8)}…
              </td>
              <td style={{ padding: "8px 12px", color: "#d1d5db" }}>{o.restaurant_id}</td>
              <td style={{ padding: "8px 12px" }}><Badge status={o.status} /></td>
              <td style={{ padding: "8px 12px", color: "#6b7280" }}>
                {new Date(o.placed_at).toLocaleTimeString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
