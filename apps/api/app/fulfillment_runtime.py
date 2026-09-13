from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .channel_runtime import adapter_for
from .foundation_models import utcnow
from .foundation_runtime import default_company_id, enqueue_outbox
from .models import ChannelAccount, ChannelOrderLink, CommerceOrder, CommerceOrderItem, MasterProduct, Supplier, SupplierProduct
from .operations_models import (
    FulfillmentItem,
    FulfillmentOrder,
    InventoryBalance,
    InventoryLocation,
    InventoryMovement,
    InventoryReservation,
    Shipment,
    SupplierFulfillmentRequest,
)

OWN_MODES = {"OWN_STOCK", "THIRD_PARTY_3PL"}


def _atp(balance: InventoryBalance) -> int:
    return max(int(balance.on_hand) - int(balance.reserved) - int(balance.safety_stock), 0)


def inventory_snapshot(db: Session, *, company_id: int | None = None) -> list[dict[str, Any]]:
    company_id = company_id or default_company_id(db)
    rows = db.scalars(select(InventoryBalance).where(InventoryBalance.company_id == company_id)).all()
    output = []
    for balance in rows:
        product = db.get(MasterProduct, balance.master_product_id)
        location = db.get(InventoryLocation, balance.location_id)
        output.append({
            "balance_id": balance.id,
            "sku": product.sku if product else "",
            "product_name": product.name if product else "",
            "location_code": location.code if location else "",
            "location_type": location.location_type if location else "",
            "on_hand": balance.on_hand,
            "reserved": balance.reserved,
            "safety_stock": balance.safety_stock,
            "available_to_promise": _atp(balance),
            "reorder_point": balance.reorder_point,
        })
    return sorted(output, key=lambda x: (x["sku"], x["location_code"]))


def adjust_inventory(db: Session, *, master_product_id: int, quantity_delta: int,
                     location_code: str = "OWN-DEFAULT", location_type: str = "OWN_STOCK",
                     safety_stock: int | None = None, reorder_point: int | None = None,
                     idempotency_key: str, note: str = "", company_id: int | None = None) -> InventoryBalance:
    company_id = company_id or default_company_id(db)
    existing = db.scalar(select(InventoryMovement).where(
        InventoryMovement.company_id == company_id,
        InventoryMovement.idempotency_key == idempotency_key,
    ))
    if existing:
        return db.get(InventoryBalance, existing.balance_id)

    location = db.scalar(select(InventoryLocation).where(
        InventoryLocation.company_id == company_id,
        InventoryLocation.code == location_code,
    ))
    if location is None:
        location = InventoryLocation(company_id=company_id, code=location_code, name=location_code, location_type=location_type)
        db.add(location)
        db.flush()
    balance = db.scalar(select(InventoryBalance).where(
        InventoryBalance.company_id == company_id,
        InventoryBalance.location_id == location.id,
        InventoryBalance.master_product_id == master_product_id,
    ))
    if balance is None:
        balance = InventoryBalance(company_id=company_id, location_id=location.id, master_product_id=master_product_id)
        db.add(balance)
        db.flush()
    if balance.on_hand + quantity_delta < 0:
        raise ValueError("inventory adjustment would make on_hand negative")
    balance.on_hand += quantity_delta
    if safety_stock is not None:
        balance.safety_stock = max(int(safety_stock), 0)
    if reorder_point is not None:
        balance.reorder_point = max(int(reorder_point), 0)
    db.add(InventoryMovement(
        company_id=company_id, balance_id=balance.id, movement_type="ADJUSTMENT",
        on_hand_delta=quantity_delta, reserved_delta=0, reference_type="MANUAL",
        reference_id="", idempotency_key=idempotency_key, note=note,
    ))
    db.commit()
    db.refresh(balance)
    return balance


def _best_stock_balance(db: Session, *, company_id: int, master_product_id: int, quantity: int) -> InventoryBalance | None:
    eligible: list[tuple[InventoryBalance, int]] = []
    rows = db.scalars(select(InventoryBalance).where(
        InventoryBalance.company_id == company_id,
        InventoryBalance.master_product_id == master_product_id,
    )).all()
    for balance in rows:
        location = db.get(InventoryLocation, balance.location_id)
        if location and location.active and location.location_type in OWN_MODES and _atp(balance) >= quantity:
            eligible.append((balance, _atp(balance)))
    eligible.sort(key=lambda x: x[1], reverse=True)
    return eligible[0][0] if eligible else None


def _dropship_supplier_product(db: Session, master_product_id: int) -> SupplierProduct | None:
    rows = db.scalars(select(SupplierProduct).where(SupplierProduct.master_product_id == master_product_id)).all()
    for row in rows:
        supplier = db.get(Supplier, row.supplier_id)
        if supplier and supplier.supports_dropship:
            return row
    return None


def _reserve(db: Session, *, company_id: int, order: CommerceOrder, item: CommerceOrderItem,
             balance: InventoryBalance) -> InventoryReservation:
    existing = db.scalar(select(InventoryReservation).where(
        InventoryReservation.company_id == company_id,
        InventoryReservation.commerce_order_item_id == item.id,
    ))
    if existing:
        return existing
    if _atp(balance) < item.quantity:
        raise ValueError("insufficient ATP")
    balance.reserved += item.quantity
    movement_key = f"RESERVE:{company_id}:{order.id}:{item.id}"
    db.add(InventoryMovement(
        company_id=company_id, balance_id=balance.id, movement_type="ORDER_RESERVE",
        on_hand_delta=0, reserved_delta=item.quantity, reference_type="ORDER_ITEM",
        reference_id=str(item.id), idempotency_key=movement_key,
    ))
    reservation = InventoryReservation(
        company_id=company_id, commerce_order_id=order.id, commerce_order_item_id=item.id,
        balance_id=balance.id, quantity=item.quantity, status="ACTIVE",
    )
    db.add(reservation)
    db.flush()
    return reservation


def allocate_order(db: Session, order: CommerceOrder, *, channel_account_id: int | None = None,
                   company_id: int | None = None) -> FulfillmentOrder:
    company_id = company_id or default_company_id(db)
    existing = db.scalar(select(FulfillmentOrder).where(
        FulfillmentOrder.company_id == company_id,
        FulfillmentOrder.commerce_order_id == order.id,
    ))
    if existing:
        return existing

    fulfillment = FulfillmentOrder(company_id=company_id, commerce_order_id=order.id,
                                   channel_account_id=channel_account_id, status="ALLOCATING")
    db.add(fulfillment)
    db.flush()
    modes: set[str] = set()
    exceptions: list[str] = []
    dropship_groups: dict[int, list[dict[str, Any]]] = {}
    estimated_costs: dict[int, Decimal] = {}

    items = db.scalars(select(CommerceOrderItem).where(CommerceOrderItem.commerce_order_id == order.id)).all()
    for item in items:
        if not item.master_product_id:
            db.add(FulfillmentItem(fulfillment_order_id=fulfillment.id, commerce_order_item_id=item.id,
                                   master_product_id=None, quantity=item.quantity,
                                   fulfillment_mode="UNMAPPED", status="EXCEPTION"))
            exceptions.append(f"unmapped SKU {item.sku or item.id}")
            continue
        balance = _best_stock_balance(db, company_id=company_id,
                                      master_product_id=item.master_product_id, quantity=item.quantity)
        if balance:
            _reserve(db, company_id=company_id, order=order, item=item, balance=balance)
            location = db.get(InventoryLocation, balance.location_id)
            mode = location.location_type if location else "OWN_STOCK"
            modes.add(mode)
            db.add(FulfillmentItem(fulfillment_order_id=fulfillment.id, commerce_order_item_id=item.id,
                                   master_product_id=item.master_product_id, quantity=item.quantity,
                                   fulfillment_mode=mode, inventory_balance_id=balance.id, status="ALLOCATED"))
            continue
        supplier_product = _dropship_supplier_product(db, item.master_product_id)
        if supplier_product:
            modes.add("SUPPLIER_DROPSHIP")
            db.add(FulfillmentItem(fulfillment_order_id=fulfillment.id, commerce_order_item_id=item.id,
                                   master_product_id=item.master_product_id, quantity=item.quantity,
                                   fulfillment_mode="SUPPLIER_DROPSHIP",
                                   supplier_product_id=supplier_product.id, status="AWAITING_SUPPLIER"))
            dropship_groups.setdefault(supplier_product.supplier_id, []).append({
                "commerce_order_item_id": item.id, "sku": item.sku,
                "supplier_sku": supplier_product.supplier_sku, "quantity": item.quantity,
            })
            estimated_costs[supplier_product.supplier_id] = (
                estimated_costs.get(supplier_product.supplier_id, Decimal("0"))
                + Decimal(str(supplier_product.supplier_price or 0)) * item.quantity
            )
            continue
        db.add(FulfillmentItem(fulfillment_order_id=fulfillment.id, commerce_order_item_id=item.id,
                               master_product_id=item.master_product_id, quantity=item.quantity,
                               fulfillment_mode="UNALLOCATED", status="EXCEPTION"))
        exceptions.append(f"no stock or dropship supplier for {item.sku}")

    db.flush()
    for supplier_id, line_items in dropship_groups.items():
        db.add(SupplierFulfillmentRequest(
            company_id=company_id, fulfillment_order_id=fulfillment.id, supplier_id=supplier_id,
            status="REQUESTED", line_items_json=json.dumps(line_items, ensure_ascii=False),
            estimated_purchase_cost=estimated_costs[supplier_id],
        ))
    if exceptions:
        fulfillment.status = "EXCEPTION"
        fulfillment.exception_reason = "; ".join(exceptions)
    elif dropship_groups:
        fulfillment.status = "AWAITING_SUPPLIER"
    else:
        fulfillment.status = "READY_TO_SHIP"
    fulfillment.mode_summary = ",".join(sorted(modes))
    db.flush()
    enqueue_outbox(db, company_id=company_id, aggregate_type="FULFILLMENT_ORDER",
                   aggregate_id=str(fulfillment.id), event_type="FULFILLMENT_ALLOCATED",
                   payload={"commerce_order_id": order.id, "status": fulfillment.status, "modes": sorted(modes)})
    db.commit()
    db.refresh(fulfillment)
    return fulfillment


def allocate_unallocated_orders(db: Session, *, channel_account_id: int | None = None,
                                company_id: int | None = None) -> dict[str, int]:
    company_id = company_id or default_company_id(db)
    if channel_account_id is not None:
        links = db.scalars(select(ChannelOrderLink).where(ChannelOrderLink.channel_account_id == channel_account_id)).all()
        orders = [db.get(CommerceOrder, x.commerce_order_id) for x in links]
    else:
        orders = db.scalars(select(CommerceOrder)).all()
    created = 0
    for order in orders:
        if not order:
            continue
        existed = db.scalar(select(FulfillmentOrder.id).where(
            FulfillmentOrder.company_id == company_id,
            FulfillmentOrder.commerce_order_id == order.id,
        ))
        allocate_order(db, order, channel_account_id=channel_account_id, company_id=company_id)
        if existed is None:
            created += 1
    return {"created": created}


def acknowledge_supplier_request(db: Session, request: SupplierFulfillmentRequest, *,
                                 external_request_id: str = "", note: str = "") -> SupplierFulfillmentRequest:
    if request.status in {"ACKNOWLEDGED", "SHIPPED"}:
        return request
    request.status = "ACKNOWLEDGED"
    request.external_request_id = external_request_id or request.external_request_id
    request.supplier_note = note
    request.acknowledged_at = utcnow()
    supplier_product_ids = {x.id for x in db.scalars(
        select(SupplierProduct).where(SupplierProduct.supplier_id == request.supplier_id)).all()}
    items = db.scalars(select(FulfillmentItem).where(
        FulfillmentItem.fulfillment_order_id == request.fulfillment_order_id)).all()
    for item in items:
        if item.supplier_product_id in supplier_product_ids and item.status == "AWAITING_SUPPLIER":
            item.status = "ALLOCATED"
    remaining = db.scalar(select(SupplierFulfillmentRequest.id).where(
        SupplierFulfillmentRequest.fulfillment_order_id == request.fulfillment_order_id,
        SupplierFulfillmentRequest.status == "REQUESTED").limit(1))
    fulfillment = db.get(FulfillmentOrder, request.fulfillment_order_id)
    if fulfillment and remaining is None and fulfillment.status != "EXCEPTION":
        fulfillment.status = "READY_TO_SHIP"
    db.commit()
    db.refresh(request)
    return request


async def ship_fulfillment(db: Session, fulfillment: FulfillmentOrder, *, carrier: str,
                           tracking_number: str, tracking_url: str = "") -> dict[str, Any]:
    company_id = fulfillment.company_id
    idem = f"SHIP:{company_id}:{fulfillment.id}:{tracking_number}"
    existing = db.scalar(select(Shipment).where(Shipment.company_id == company_id, Shipment.idempotency_key == idem))
    if existing:
        return {"status": "DUPLICATE", "shipment_id": existing.id, "tracking_number": existing.tracking_number}
    if fulfillment.status in {"CANCELLED", "EXCEPTION"}:
        raise ValueError(f"cannot ship fulfillment in status {fulfillment.status}")
    if fulfillment.status == "AWAITING_SUPPLIER":
        raise ValueError("supplier must acknowledge dropship request before shipment")

    items = db.scalars(select(FulfillmentItem).where(FulfillmentItem.fulfillment_order_id == fulfillment.id)).all()
    for item in items:
        if item.inventory_balance_id:
            reservation = db.scalar(select(InventoryReservation).where(
                InventoryReservation.company_id == company_id,
                InventoryReservation.commerce_order_item_id == item.commerce_order_item_id,
                InventoryReservation.status == "ACTIVE"))
            if reservation:
                balance = db.get(InventoryBalance, reservation.balance_id)
                if balance.on_hand < reservation.quantity or balance.reserved < reservation.quantity:
                    raise ValueError("inventory invariant violated while shipping")
                balance.on_hand -= reservation.quantity
                balance.reserved -= reservation.quantity
                db.add(InventoryMovement(
                    company_id=company_id, balance_id=balance.id, movement_type="SHIP_CONSUME",
                    on_hand_delta=-reservation.quantity, reserved_delta=-reservation.quantity,
                    reference_type="FULFILLMENT_ITEM", reference_id=str(item.id),
                    idempotency_key=f"SHIP_CONSUME:{company_id}:{fulfillment.id}:{item.id}",
                ))
                reservation.status = "CONSUMED"
                reservation.closed_at = utcnow()
        item.status = "SHIPPED"
    for request in db.scalars(select(SupplierFulfillmentRequest).where(
        SupplierFulfillmentRequest.fulfillment_order_id == fulfillment.id)).all():
        if request.status == "ACKNOWLEDGED":
            request.status = "SHIPPED"

    shipment = Shipment(company_id=company_id, fulfillment_order_id=fulfillment.id, carrier=carrier,
                        tracking_number=tracking_number, tracking_url=tracking_url,
                        status="SHIPPED", idempotency_key=idem)
    db.add(shipment)
    fulfillment.status = "SHIPPED"
    db.flush()

    channel_result: dict[str, Any] = {"status": "LOCAL_ONLY"}
    link = db.scalar(select(ChannelOrderLink).where(ChannelOrderLink.commerce_order_id == fulfillment.commerce_order_id))
    if link and fulfillment.channel_account_id:
        account = db.get(ChannelAccount, fulfillment.channel_account_id)
        if account:
            channel_result = await adapter_for(account).ship_order(link.external_order_id, tracking_number)
    enqueue_outbox(db, company_id=company_id, aggregate_type="FULFILLMENT_ORDER",
                   aggregate_id=str(fulfillment.id), event_type="FULFILLMENT_SHIPPED",
                   payload={"tracking_number": tracking_number, "carrier": carrier})
    db.commit()
    return {"status": "SHIPPED", "shipment_id": shipment.id,
            "tracking_number": tracking_number, "channel_result": channel_result}


def cancel_fulfillment(db: Session, fulfillment: FulfillmentOrder, *, reason: str = "") -> dict[str, Any]:
    if fulfillment.status == "CANCELLED":
        return {"status": "CANCELLED", "duplicate": True}
    if fulfillment.status == "SHIPPED":
        raise ValueError("shipped fulfillment cannot be cancelled; create return workflow")
    reservations = db.scalars(select(InventoryReservation).where(
        InventoryReservation.company_id == fulfillment.company_id,
        InventoryReservation.commerce_order_id == fulfillment.commerce_order_id,
        InventoryReservation.status == "ACTIVE")).all()
    for reservation in reservations:
        balance = db.get(InventoryBalance, reservation.balance_id)
        if balance.reserved < reservation.quantity:
            raise ValueError("inventory invariant violated while releasing reservation")
        balance.reserved -= reservation.quantity
        db.add(InventoryMovement(
            company_id=fulfillment.company_id, balance_id=balance.id, movement_type="ORDER_RELEASE",
            on_hand_delta=0, reserved_delta=-reservation.quantity,
            reference_type="FULFILLMENT_ORDER", reference_id=str(fulfillment.id),
            idempotency_key=f"RELEASE:{fulfillment.company_id}:{fulfillment.id}:{reservation.id}", note=reason,
        ))
        reservation.status = "RELEASED"
        reservation.closed_at = utcnow()
    for request in db.scalars(select(SupplierFulfillmentRequest).where(
        SupplierFulfillmentRequest.fulfillment_order_id == fulfillment.id)).all():
        if request.status not in {"SHIPPED", "CANCELLED"}:
            request.status = "CANCELLED"
            request.supplier_note = reason
    fulfillment.status = "CANCELLED"
    fulfillment.exception_reason = reason
    enqueue_outbox(db, company_id=fulfillment.company_id, aggregate_type="FULFILLMENT_ORDER",
                   aggregate_id=str(fulfillment.id), event_type="FULFILLMENT_CANCELLED", payload={"reason": reason})
    db.commit()
    return {"status": "CANCELLED", "released_reservations": len(reservations)}


def fulfillment_list(db: Session, *, company_id: int | None = None) -> list[dict[str, Any]]:
    company_id = company_id or default_company_id(db)
    rows = db.scalars(select(FulfillmentOrder).where(
        FulfillmentOrder.company_id == company_id).order_by(FulfillmentOrder.id.desc())).all()
    result = []
    for f in rows:
        order = db.get(CommerceOrder, f.commerce_order_id)
        items = db.scalars(select(FulfillmentItem).where(FulfillmentItem.fulfillment_order_id == f.id)).all()
        requests = db.scalars(select(SupplierFulfillmentRequest).where(
            SupplierFulfillmentRequest.fulfillment_order_id == f.id)).all()
        shipments = db.scalars(select(Shipment).where(Shipment.fulfillment_order_id == f.id)).all()
        result.append({
            "id": f.id, "order_id": f.commerce_order_id, "order_no": order.order_no if order else "",
            "status": f.status, "mode_summary": f.mode_summary, "exception_reason": f.exception_reason,
            "items": [{"id": x.id, "quantity": x.quantity, "mode": x.fulfillment_mode, "status": x.status}
                      for x in items],
            "supplier_requests": [{"id": x.id, "supplier_id": x.supplier_id, "status": x.status,
                                   "estimated_purchase_cost": float(x.estimated_purchase_cost or 0),
                                   "external_request_id": x.external_request_id} for x in requests],
            "shipments": [{"id": x.id, "carrier": x.carrier, "tracking_number": x.tracking_number,
                           "status": x.status} for x in shipments],
        })
    return result


def operations_overview(db: Session, *, company_id: int | None = None) -> dict[str, Any]:
    company_id = company_id or default_company_id(db)
    fulfillments = fulfillment_list(db, company_id=company_id)
    inventory = inventory_snapshot(db, company_id=company_id)
    requests = db.scalars(select(SupplierFulfillmentRequest).where(
        SupplierFulfillmentRequest.company_id == company_id)).all()
    return {
        "version": "0.5B",
        "inventory": {
            "sku_locations": len(inventory), "on_hand": sum(x["on_hand"] for x in inventory),
            "reserved": sum(x["reserved"] for x in inventory),
            "available_to_promise": sum(x["available_to_promise"] for x in inventory),
            "below_reorder_point": sum(x["available_to_promise"] <= x["reorder_point"] for x in inventory),
        },
        "fulfillment": {
            "total": len(fulfillments),
            "awaiting_supplier": sum(x["status"] == "AWAITING_SUPPLIER" for x in fulfillments),
            "ready_to_ship": sum(x["status"] == "READY_TO_SHIP" for x in fulfillments),
            "shipped": sum(x["status"] == "SHIPPED" for x in fulfillments),
            "exceptions": sum(x["status"] == "EXCEPTION" for x in fulfillments),
        },
        "supplier_requests": {
            "requested": sum(x.status == "REQUESTED" for x in requests),
            "acknowledged": sum(x.status == "ACKNOWLEDGED" for x in requests),
        },
    }
