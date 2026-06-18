import { useState } from "react";

// ── Shared styles ─────────────────────────────────────────────────────────────

const input = {
  width: "100%", padding: "8px 10px", background: "#0f1117",
  border: "1px solid #374151", borderRadius: 6, color: "#e5e7eb",
  fontSize: 13, outline: "none", boxSizing: "border-box",
};
const label = { fontSize: 12, color: "#9ca3af", display: "block", marginBottom: 4 };
const field = { marginBottom: 12 };
const btn = (color = "#10b981", disabled = false) => ({
  padding: "9px 20px", background: disabled ? "#374151" : color,
  color: disabled ? "#6b7280" : "#0f1117", border: "none", borderRadius: 6,
  fontWeight: 700, fontSize: 13, cursor: disabled ? "not-allowed" : "pointer",
});

function ResponseBox({ response }) {
  if (!response) return null;
  const isError = response.status >= 400;
  return (
    <div style={{
      marginTop: 16, background: "#0f1117", border: `1px solid ${isError ? "#ef4444" : "#10b981"}`,
      borderRadius: 6, padding: 12,
    }}>
      <div style={{ fontSize: 11, color: isError ? "#ef4444" : "#10b981", marginBottom: 6, fontWeight: 700 }}>
        HTTP {response.status} {response.statusText}
      </div>
      <pre style={{ fontSize: 12, color: "#d1d5db", whiteSpace: "pre-wrap", wordBreak: "break-all", margin: 0 }}>
        {JSON.stringify(response.body, null, 2)}
      </pre>
    </div>
  );
}

async function callApi(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  let json;
  try { json = await res.json(); } catch { json = {}; }
  return { status: res.status, statusText: res.statusText, body: json };
}

// ── Restaurants & menu data ───────────────────────────────────────────────────

const RESTAURANTS = Array.from({ length: 10 }, (_, i) => `rest-${String(i + 1).padStart(2, "0")}`);
const MENU = ["Burger", "Pizza", "Sushi", "Pasta", "Salad", "Tacos", "Ramen", "Curry", "Wrap", "Steak"];
const STATUSES = ["placed", "confirmed", "preparing", "ready", "out_for_delivery", "delivered", "failed", "cancelled", "dead_lettered"];

// ── Tab: Place Order ──────────────────────────────────────────────────────────

function PlaceOrder({ onOrderPlaced }) {
  const [restaurantId, setRestaurantId] = useState(RESTAURANTS[0]);
  const [customerId,   setCustomerId]   = useState("cust-0001");
  const [items,        setItems]        = useState([{ name: "Burger", quantity: 1, price: 12.50 }]);
  const [loading,      setLoading]      = useState(false);
  const [response,     setResponse]     = useState(null);

  const total = items.reduce((s, i) => s + i.quantity * i.price, 0);

  const addItem = () => setItems(prev => [...prev, { name: MENU[0], quantity: 1, price: 10 }]);
  const removeItem = (idx) => setItems(prev => prev.filter((_, i) => i !== idx));
  const updateItem = (idx, key, val) =>
    setItems(prev => prev.map((it, i) => i === idx ? { ...it, [key]: val } : it));

  const submit = async () => {
    setLoading(true);
    const r = await callApi("POST", "/orders", {
      customer_id:   customerId,
      restaurant_id: restaurantId,
      items:         items.map(i => ({ ...i, price: parseFloat(i.price), quantity: parseInt(i.quantity) })),
      total_amount:  parseFloat(total.toFixed(2)),
    });
    setResponse(r);
    setLoading(false);
    if (r.status === 202) onOrderPlaced?.(r.body.order_id);
  };

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
        <div style={field}>
          <label style={label}>Customer ID</label>
          <input style={input} value={customerId} onChange={e => setCustomerId(e.target.value)} />
        </div>
        <div style={field}>
          <label style={label}>Restaurant</label>
          <select style={input} value={restaurantId} onChange={e => setRestaurantId(e.target.value)}>
            {RESTAURANTS.map(r => <option key={r}>{r}</option>)}
          </select>
        </div>
      </div>

      <label style={label}>Items</label>
      {items.map((item, idx) => (
        <div key={idx} style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr auto", gap: 8, marginBottom: 8, alignItems: "center" }}>
          <select style={input} value={item.name} onChange={e => updateItem(idx, "name", e.target.value)}>
            {MENU.map(m => <option key={m}>{m}</option>)}
          </select>
          <input style={input} type="number" min="1" max="10" value={item.quantity}
            onChange={e => updateItem(idx, "quantity", e.target.value)} placeholder="Qty" />
          <input style={input} type="number" min="1" step="0.5" value={item.price}
            onChange={e => updateItem(idx, "price", e.target.value)} placeholder="Price $" />
          <button onClick={() => removeItem(idx)}
            style={{ background: "none", border: "1px solid #374151", color: "#ef4444", borderRadius: 4, padding: "4px 10px", cursor: "pointer", fontSize: 16 }}>
            ×
          </button>
        </div>
      ))}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
        <button onClick={addItem} style={{ background: "none", border: "1px solid #374151", color: "#9ca3af", borderRadius: 6, padding: "6px 14px", cursor: "pointer", fontSize: 12 }}>
          + Add item
        </button>
        <span style={{ color: "#9ca3af", fontSize: 13 }}>Total: <strong style={{ color: "#e5e7eb" }}>${total.toFixed(2)}</strong></span>
      </div>

      <button onClick={submit} disabled={loading} style={{ ...btn("#10b981", loading), marginTop: 16, width: "100%" }}>
        {loading ? "Placing…" : "Place Order"}
      </button>

      <ResponseBox response={response} />
    </div>
  );
}

// ── Tab: List Orders ──────────────────────────────────────────────────────────

function ListOrders({ onSelectOrder }) {
  const [status,     setStatus]     = useState("");
  const [restaurant, setRestaurant] = useState("");
  const [page,       setPage]       = useState(1);
  const [perPage,    setPerPage]    = useState(20);
  const [loading,    setLoading]    = useState(false);
  const [response,   setResponse]   = useState(null);

  const fetch_ = async () => {
    setLoading(true);
    const params = new URLSearchParams({ page, per_page: perPage });
    if (status)     params.set("status", status);
    if (restaurant) params.set("restaurant_id", restaurant);
    const r = await callApi("GET", `/orders?${params}`);
    setResponse(r);
    setLoading(false);
  };

  const orders = response?.body?.orders ?? [];

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr auto", gap: 10, alignItems: "flex-end", marginBottom: 16 }}>
        <div>
          <label style={label}>Status filter</label>
          <select style={input} value={status} onChange={e => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {STATUSES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label style={label}>Restaurant filter</label>
          <select style={input} value={restaurant} onChange={e => setRestaurant(e.target.value)}>
            <option value="">All restaurants</option>
            {RESTAURANTS.map(r => <option key={r}>{r}</option>)}
          </select>
        </div>
        <div>
          <label style={label}>Page</label>
          <input style={input} type="number" min="1" value={page} onChange={e => setPage(e.target.value)} />
        </div>
        <div>
          <label style={label}>Per page</label>
          <select style={input} value={perPage} onChange={e => setPerPage(e.target.value)}>
            {[10, 20, 50, 100].map(n => <option key={n}>{n}</option>)}
          </select>
        </div>
        <button onClick={fetch_} disabled={loading} style={btn("#3b82f6", loading)}>
          {loading ? "…" : "Fetch"}
        </button>
      </div>

      {response && (
        <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>
          HTTP {response.status} — {response.body?.total ?? 0} total orders
        </div>
      )}

      {orders.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #374151", color: "#6b7280" }}>
                {["Order ID", "Customer", "Restaurant", "Status", "Total", "Placed At"].map(h => (
                  <th key={h} style={{ textAlign: "left", padding: "6px 10px", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orders.map(o => (
                <tr key={o.order_id}
                  onClick={() => onSelectOrder(o.order_id)}
                  style={{ borderBottom: "1px solid #1f2937", cursor: "pointer" }}
                  onMouseEnter={e => e.currentTarget.style.background = "#1f2937"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <td style={{ padding: "6px 10px", fontFamily: "monospace", color: "#6366f1" }}>
                    {o.order_id.slice(0, 8)}…
                  </td>
                  <td style={{ padding: "6px 10px", color: "#d1d5db" }}>{o.customer_id}</td>
                  <td style={{ padding: "6px 10px", color: "#d1d5db" }}>{o.restaurant_id}</td>
                  <td style={{ padding: "6px 10px" }}>
                    <StatusBadge status={o.status} />
                  </td>
                  <td style={{ padding: "6px 10px", color: "#d1d5db" }}>${o.total_amount}</td>
                  <td style={{ padding: "6px 10px", color: "#6b7280" }}>
                    {new Date(o.placed_at).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 11, color: "#4b5563", marginTop: 8 }}>Click a row to load it in "Get Order"</p>
        </div>
      )}

      {orders.length === 0 && response && (
        <p style={{ color: "#6b7280", fontSize: 13 }}>No orders found.</p>
      )}
    </div>
  );
}

// ── Tab: Get Order ────────────────────────────────────────────────────────────

function GetOrder({ prefillId }) {
  const [orderId,  setOrderId]  = useState(prefillId ?? "");
  const [loading,  setLoading]  = useState(false);
  const [response, setResponse] = useState(null);

  // When a row is clicked in List Orders, prefillId updates
  if (prefillId && prefillId !== orderId && !loading) {
    setOrderId(prefillId);
  }

  const fetch_ = async () => {
    if (!orderId.trim()) return;
    setLoading(true);
    const r = await callApi("GET", `/orders/${orderId.trim()}`);
    setResponse(r);
    setLoading(false);
  };

  const order  = response?.body;
  const events = order?.events ?? [];

  return (
    <div>
      <div style={{ display: "flex", gap: 10 }}>
        <input
          style={{ ...input, flex: 1 }}
          placeholder="Paste an order UUID…"
          value={orderId}
          onChange={e => setOrderId(e.target.value)}
          onKeyDown={e => e.key === "Enter" && fetch_()}
        />
        <button onClick={fetch_} disabled={loading || !orderId.trim()} style={btn("#3b82f6", loading || !orderId.trim())}>
          {loading ? "…" : "Get"}
        </button>
      </div>

      {response && response.status === 200 && order && (
        <div style={{ marginTop: 16 }}>
          {/* Order summary */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginBottom: 16 }}>
            {[
              ["Order ID",    order.order_id?.slice(0, 18) + "…"],
              ["Status",      order.status],
              ["Customer",    order.customer_id],
              ["Restaurant",  order.restaurant_id],
              ["Total",       `$${order.total_amount}`],
              ["Placed",      new Date(order.placed_at).toLocaleString()],
            ].map(([k, v]) => (
              <div key={k} style={{ background: "#0f1117", borderRadius: 6, padding: "8px 12px", border: "1px solid #1f2937" }}>
                <div style={{ fontSize: 10, color: "#6b7280", marginBottom: 2 }}>{k}</div>
                <div style={{ fontSize: 13, color: "#e5e7eb", fontWeight: 600 }}>{v}</div>
              </div>
            ))}
          </div>

          {/* Items */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 6, textTransform: "uppercase" }}>Items</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {(order.items ?? []).map((it, i) => (
                <span key={i} style={{ background: "#1f2937", borderRadius: 4, padding: "4px 10px", fontSize: 12, color: "#d1d5db" }}>
                  {it.name} × {it.quantity} — ${it.price}
                </span>
              ))}
            </div>
          </div>

          {/* Audit trail */}
          <div>
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 8, textTransform: "uppercase" }}>Audit Trail</div>
            <div style={{ position: "relative", paddingLeft: 20 }}>
              <div style={{ position: "absolute", left: 7, top: 0, bottom: 0, width: 2, background: "#1f2937" }} />
              {events.map((ev, i) => (
                <div key={ev.id} style={{ position: "relative", marginBottom: 12 }}>
                  <div style={{
                    position: "absolute", left: -17, top: 4, width: 10, height: 10,
                    borderRadius: "50%", background: i === events.length - 1 ? "#10b981" : "#374151",
                    border: "2px solid #0f1117",
                  }} />
                  <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
                    <span style={{ fontSize: 12, color: "#e5e7eb", fontWeight: 600 }}>
                      {ev.from_status ? `${ev.from_status} → ` : ""}{ev.to_status}
                    </span>
                    <span style={{ fontSize: 11, color: "#6b7280" }}>
                      {new Date(ev.created_at).toLocaleTimeString()}
                    </span>
                    {ev.worker_id && (
                      <span style={{ fontSize: 10, color: "#4b5563" }}>{ev.worker_id}</span>
                    )}
                  </div>
                  {ev.reason && (
                    <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>{ev.reason}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {response && response.status !== 200 && <ResponseBox response={response} />}
    </div>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────

const STATUS_COLOR = {
  placed: "#6366f1", confirmed: "#3b82f6", preparing: "#f59e0b",
  ready: "#10b981", out_for_delivery: "#8b5cf6", delivered: "#22c55e",
  failed: "#ef4444", cancelled: "#6b7280", dead_lettered: "#dc2626",
};

function StatusBadge({ status }) {
  const color = STATUS_COLOR[status] ?? "#9ca3af";
  return (
    <span style={{
      background: color + "22", color, border: `1px solid ${color}`,
      borderRadius: 4, padding: "2px 7px", fontSize: 11, fontWeight: 600, whiteSpace: "nowrap",
    }}>
      {status}
    </span>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────

const TABS = ["Place Order", "List Orders", "Get Order"];

export default function ApiExplorer({ onOrderPlaced }) {
  const [activeTab,   setActiveTab]   = useState("Place Order");
  const [selectedId,  setSelectedId]  = useState(null);

  const handleOrderPlaced = (id) => {
    onOrderPlaced?.(id);
    setSelectedId(id);
  };

  const handleSelectOrder = (id) => {
    setSelectedId(id);
    setActiveTab("Get Order");
  };

  return (
    <div>
      {/* Tab bar */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: "1px solid #1f2937", paddingBottom: 0 }}>
        {TABS.map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            background: "none", border: "none", padding: "8px 16px",
            color: activeTab === tab ? "#e5e7eb" : "#6b7280",
            fontWeight: activeTab === tab ? 700 : 400,
            fontSize: 13, cursor: "pointer",
            borderBottom: activeTab === tab ? "2px solid #6366f1" : "2px solid transparent",
            marginBottom: -1,
          }}>
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "Place Order" && <PlaceOrder onOrderPlaced={handleOrderPlaced} />}
      {activeTab === "List Orders" && <ListOrders onSelectOrder={handleSelectOrder} />}
      {activeTab === "Get Order"   && <GetOrder prefillId={selectedId} />}
    </div>
  );
}
