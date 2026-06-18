const BASE = "";

export async function fetchStats() {
  const res = await fetch(`${BASE}/api/stats`);
  if (!res.ok) throw new Error("stats fetch failed");
  return res.json();
}

export async function fetchRecentOrders(limit = 50) {
  const res = await fetch(`${BASE}/orders?per_page=${limit}`);
  if (!res.ok) throw new Error("orders fetch failed");
  return res.json();
}
