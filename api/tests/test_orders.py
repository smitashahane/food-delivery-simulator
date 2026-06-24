"""Tests for POST /orders and GET /orders endpoints."""
import uuid

VALID_ORDER = {
    "customer_id":   "cust-test",
    "restaurant_id": "rest-01",
    "items":         [{"name": "Burger", "quantity": 1, "price": 12.50}],
    "total_amount":  12.50,
}


def test_place_order_returns_202(client):
    r = client.post("/orders", json=VALID_ORDER)
    assert r.status_code == 202
    body = r.get_json()
    assert "order_id" in body
    assert body["status"] == "placed"
    assert "placed_at" in body


def test_place_order_missing_field_returns_400(client):
    bad = {k: v for k, v in VALID_ORDER.items() if k != "restaurant_id"}
    r = client.post("/orders", json=bad)
    assert r.status_code == 400
    assert "restaurant_id" in r.get_json()["error"]


def test_place_order_empty_items_returns_400(client):
    r = client.post("/orders", json={**VALID_ORDER, "items": []})
    assert r.status_code == 400


def test_duplicate_order_id_returns_409(client):
    order_id = str(uuid.uuid4())
    body = {**VALID_ORDER, "order_id": order_id}
    r1 = client.post("/orders", json=body)
    assert r1.status_code == 202
    r2 = client.post("/orders", json=body)
    assert r2.status_code == 409


def test_get_order_returns_events(client):
    r = client.post("/orders", json=VALID_ORDER)
    oid = r.get_json()["order_id"]
    r2 = client.get(f"/orders/{oid}")
    assert r2.status_code == 200
    body = r2.get_json()
    assert body["status"] == "placed"
    assert len(body["events"]) == 1
    assert body["events"][0]["to_status"] == "placed"


def test_get_order_not_found(client):
    r = client.get(f"/orders/{uuid.uuid4()}")
    assert r.status_code == 404


def test_list_orders_filter_by_status(client):
    client.post("/orders", json=VALID_ORDER)
    r = client.get("/orders?status=placed")
    assert r.status_code == 200
    body = r.get_json()
    assert body["total"] >= 1
    assert all(o["status"] == "placed" for o in body["orders"])


def test_list_orders_invalid_status_returns_400(client):
    r = client.get("/orders?status=nonexistent")
    assert r.status_code == 400
