import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Numeric, DateTime, ForeignKey,
    Text, Index, Enum as SAEnum, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class OrderStatus(str, PyEnum):
    PLACED = "placed"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


def _now():
    return datetime.now(timezone.utc)


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(String(255), nullable=False)
    restaurant_id = Column(String(255), nullable=False)
    items = Column(JSON, nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    status = Column(
        SAEnum(OrderStatus, name="order_status", create_type=True),
        nullable=False,
        default=OrderStatus.PLACED,
    )
    placed_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    events = relationship(
        "OrderEvent", back_populates="order",
        order_by="OrderEvent.created_at", lazy="select"
    )

    __table_args__ = (
        Index("ix_orders_status", "status"),
        Index("ix_orders_placed_at", "placed_at"),
        Index("ix_orders_restaurant_id", "restaurant_id"),
    )

    def to_dict(self, include_events=False):
        d = {
            "order_id": str(self.id),
            "customer_id": self.customer_id,
            "restaurant_id": self.restaurant_id,
            "items": self.items,
            "total_amount": str(self.total_amount),
            "status": self.status.value,
            "placed_at": self.placed_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_events:
            d["events"] = [e.to_dict() for e in self.events]
        return d


class OrderEvent(Base):
    __tablename__ = "order_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    from_status = Column(SAEnum(OrderStatus, name="order_status", create_type=False), nullable=True)
    to_status = Column(SAEnum(OrderStatus, name="order_status", create_type=False), nullable=False)
    worker_id = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    order = relationship("Order", back_populates="events")

    __table_args__ = (
        Index("ix_order_events_order_id", "order_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "order_id": str(self.order_id),
            "from_status": self.from_status.value if self.from_status else None,
            "to_status": self.to_status.value,
            "worker_id": self.worker_id,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }
