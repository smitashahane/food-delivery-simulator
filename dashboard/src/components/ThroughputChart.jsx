import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

export default function ThroughputChart({ history }) {
  if (!history?.length) {
    return <p style={{ color: "#6b7280", padding: 16 }}>Waiting for data…</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={history}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
        <XAxis dataKey="t" tick={{ fill: "#6b7280", fontSize: 11 }} />
        <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} />
        <Tooltip
          contentStyle={{ background: "#1f2937", border: "1px solid #374151", color: "#e5e7eb" }}
        />
        <Line type="monotone" dataKey="opm" stroke="#10b981" dot={false} strokeWidth={2} name="orders/min" />
      </LineChart>
    </ResponsiveContainer>
  );
}
