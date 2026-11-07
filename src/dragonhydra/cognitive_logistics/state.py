"""Owned fictional inventory: FEFO lots, reservations and single-owner transit."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

SCHEMA = "dragonhydra.logistics-inventory/1"


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise ValueError("LOGISTICS_IDENTIFIER_INVALID")
    return value


def integer(value, low=0, high=10**9):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("LOGISTICS_INTEGER_INVALID")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def key(prefix, value):
    return prefix + hashlib.sha256(canonical(value).encode()).hexdigest()[:24]


class InventoryState:
    def __init__(self, config):
        if not isinstance(config, dict) or set(config) - {"nodes", "initial", "shelf_life", "initial_day"}:
            raise ValueError("LOGISTICS_INVENTORY_CONFIG_INVALID")
        nodes = config.get("nodes")
        if not isinstance(nodes, dict) or not 1 <= len(nodes) <= 32:
            raise ValueError("LOGISTICS_NODES_INVALID")
        normalized = {}
        for name, node in nodes.items():
            identifier(name)
            if not isinstance(node, dict) or set(node) != {"kind", "capacity"}:
                raise ValueError("LOGISTICS_NODE_INVALID")
            normalized[name] = {"kind": identifier(node["kind"]), "capacity": integer(node["capacity"])}
        initial = config.get("initial", {})
        if not isinstance(initial, dict) or set(initial) - set(nodes):
            raise ValueError("LOGISTICS_INITIAL_LOCATION_INVALID")
        initial = deepcopy(initial)
        skus = set()
        for location, values in initial.items():
            if not isinstance(values, dict):
                raise ValueError("LOGISTICS_INITIAL_STOCK_INVALID")
            for sku, quantity in values.items():
                identifier(sku); integer(quantity); skus.add(sku)
            if sum(values.values()) > normalized[location]["capacity"]:
                raise ValueError("LOGISTICS_CAPACITY_EXCEEDED")
        if len(skus) > 32:
            raise ValueError("LOGISTICS_SKU_LIMIT")
        shelf = integer(config.get("shelf_life", 14), 1, 3650)
        day = integer(config.get("initial_day", 0), 0, 100000)
        self.config = {"nodes": normalized, "initial": initial, "shelf_life": shelf, "initial_day": day}
        lots = []
        for location in sorted(initial):
            for sku, quantity in sorted(initial[location].items()):
                if quantity:
                    lots.append({"lot_id": key("initial:", [location, sku, day]), "location": location,
                                 "sku": sku, "qty": quantity, "created_day": day, "expiry_day": day+shelf})
        self._data = {"day": day, "skus": sorted(skus), "lots": lots, "reservations": {}, "orders": {},
                      "capacities":{name:node["capacity"] for name,node in normalized.items()}, "production_shelf_life":shelf,
                      "backorders": [], "totals": {"initial": sum(lot["qty"] for lot in lots), "production": 0,
                      "fulfilled": 0, "spoilage": 0, "spoiled":0, "lost_sales": 0, "demanded": 0, "backordered": 0},
                      "events": [], "operations": {}}
        self.verify_conservation()

    def to_dict(self):
        return {"schema_version": SCHEMA, "config": deepcopy(self.config), **deepcopy(self._data)}

    @classmethod
    def from_dict(cls, raw):
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA or "config" not in raw:
            raise ValueError("LOGISTICS_STATE_SCHEMA_INVALID")
        result = cls(raw["config"])
        state={k:v for k,v in raw.items() if k not in ("schema_version","config")}
        if set(state) != set(result._data):
            raise ValueError("LOGISTICS_STATE_FIELDS_INVALID")
        canonical(raw)
        result._data = deepcopy(state)
        try:
            result.verify_conservation()
        except (KeyError,TypeError,IndexError,AttributeError):
            raise ValueError("LOGISTICS_STATE_STRUCTURE_INVALID") from None
        return result

    def _location(self, location):
        if location not in self.config["nodes"]:
            raise ValueError("LOGISTICS_LOCATION_UNKNOWN")

    def _capacity(self, location):
        return self._data["capacities"][location]

    def _sku(self, sku):
        identifier(sku)
        if sku not in self._data["skus"]:
            if len(self._data["skus"]) >= 32:
                raise ValueError("LOGISTICS_SKU_LIMIT")
            self._data["skus"].append(sku)
            self._data["skus"].sort()

    def _on_hand(self, location, sku=None):
        return sum(lot["qty"] for lot in self._data["lots"] if lot["location"] == location and (sku is None or lot["sku"] == sku))

    def _reserved_by_lot(self):
        result = {}
        for reservation in self._data["reservations"].values():
            for allocation in reservation["allocations"]:
                result[allocation["lot_id"]] = result.get(allocation["lot_id"], 0) + allocation["qty"]
        return result

    def _fefo(self, location, sku, quantity, *, consume=False):
        reserved = self._reserved_by_lot()
        allocations, left = [], quantity
        for lot in sorted(self._data["lots"], key=lambda x: (x["expiry_day"], x["created_day"], x["lot_id"])):
            if lot["location"] != location or lot["sku"] != sku:
                continue
            take = min(left, lot["qty"] - reserved.get(lot["lot_id"], 0))
            if take:
                allocations.append({"lot_id": lot["lot_id"], "qty": take})
                if consume:
                    lot["qty"] -= take
                left -= take
            if not left:
                break
        if consume:
            self._data["lots"] = [lot for lot in self._data["lots"] if lot["qty"]]
        return allocations, quantity-left

    def _backfill(self, location, sku, day):
        fulfilled = late = 0
        for backorder in self._data["backorders"]:
            if backorder["location"] != location or backorder["sku"] != sku or not backorder["qty"]:
                continue
            _, quantity = self._fefo(location, sku, backorder["qty"], consume=True)
            backorder["qty"] -= quantity
            fulfilled += quantity
            late += quantity if day > backorder["created_day"] else 0
        self._data["backorders"] = [row for row in self._data["backorders"] if row["qty"]]
        self._data["totals"]["fulfilled"] += fulfilled
        return {"fulfilled_backorders": fulfilled, "late_fulfilled": late}

    def _order_status(self, order):
        reservation = self._data["reservations"]["order:"+order["order_id"]]
        if order["shipments"]:
            order["status"] = "IN_TRANSIT"
        elif reservation["allocations"]:
            order["status"] = "PLACED"
        elif order["received_qty"]:
            order["status"] = "PARTIALLY_RECEIVED" if order["spoiled_qty"] or order["cancelled_qty"] else "RECEIVED"
        else:
            order["status"] = "CANCELLED" if order["cancelled_qty"] else "SPOILED"

    def _expire(self, day):
        expired = {lot["lot_id"]: lot for lot in self._data["lots"] if lot["expiry_day"] <= day}
        oh = sum(lot["qty"] for lot in expired.values())
        for reservation in self._data["reservations"].values():
            removed = sum(a["qty"] for a in reservation["allocations"] if a["lot_id"] in expired)
            reservation["allocations"] = [a for a in reservation["allocations"] if a["lot_id"] not in expired]
            if removed and not reservation["allocations"]:
                reservation["status"] = "SPOILED"
            if removed and reservation["order_id"] is not None:
                self._data["orders"][reservation["order_id"]]["spoiled_qty"] += removed
        self._data["lots"] = [lot for lot in self._data["lots"] if lot["lot_id"] not in expired]
        transit = 0; affected = []
        for order in self._data["orders"].values():
            removed = sum(lot["qty"] for lot in order["shipments"] if lot["expiry_day"] <= day)
            order["shipments"] = [lot for lot in order["shipments"] if lot["expiry_day"] > day]
            order["spoiled_qty"] += removed; transit += removed
            old = order["status"]
            self._order_status(order)
            if removed or old != order["status"]:
                affected.append(order["order_id"])
        self._data["totals"]["spoilage"] += oh + transit
        self._data["totals"]["spoiled"] = self._data["totals"]["spoilage"]
        return {"expired_qty": oh+transit, "expired_on_hand": oh, "expired_in_transit": transit, "affected_orders": affected}

    def _apply(self, operation_id, kind, day, payload, mutate):
        identifier(operation_id); integer(day, 0, 100000)
        fingerprint = hashlib.sha256(canonical({"type": kind, "day": day, **payload}).encode()).hexdigest()
        previous = self._data["operations"].get(operation_id)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise ValueError("LOGISTICS_OPERATION_ID_CONFLICT")
            return deepcopy(self._data["events"][previous["event_index"]])
        if day < self._data["day"]:
            raise ValueError("LOGISTICS_CLOCK_REWIND_REJECTED")
        if len(self._data["events"]) >= 100000:
            raise ValueError("LOGISTICS_EVENT_LIMIT")
        physical = {key: deepcopy(value) for key, value in self._data.items() if key not in ("events", "operations")}
        try:
            self._data["day"] = day
            expiry = self._expire(day)
            detail = mutate(expiry)
            self.verify_conservation()
            receipt = {"schema_version": "dragonhydra.logistics-operation/1", "synthetic": True,
                       "operation_id": operation_id, "type": kind, "day": day, "status": "APPLIED",
                       **payload, **detail, "automatic_spoilage_qty": expiry["expired_qty"]}
            canonical(receipt)
        except Exception:
            for key, value in physical.items():
                self._data[key] = value
            raise
        index = len(self._data["events"])
        self._data["events"].append(receipt)
        self._data["operations"][operation_id] = {"fingerprint": fingerprint, "event_index": index}
        return deepcopy(receipt)

    def reserve(self, reservation_id, location, sku, qty, day):
        identifier(reservation_id); self._location(location); identifier(sku); integer(qty, 1)
        def mutate(_):
            self._sku(sku)
            if reservation_id in self._data["reservations"]:
                raise ValueError("LOGISTICS_RESERVATION_EXISTS")
            allocations, filled = self._fefo(location, sku, qty)
            if filled != qty:
                raise ValueError("LOGISTICS_ATP_INSUFFICIENT")
            self._data["reservations"][reservation_id] = {"reservation_id": reservation_id, "location": location,
                "sku": sku, "qty": qty, "allocations": allocations, "status": "RESERVED", "order_id": None}
            return {"reserved_qty": qty, "allocations": deepcopy(allocations)}
        return self._apply("reserve:"+reservation_id, "RESERVE", day, {"location": location,"sku":sku,"qty":qty}, mutate)

    def release(self, reservation_id, day):
        identifier(reservation_id)
        def mutate(_):
            if reservation_id not in self._data["reservations"]:
                raise ValueError("LOGISTICS_RESERVATION_UNKNOWN")
            reservation = self._data["reservations"][reservation_id]
            qty = sum(a["qty"] for a in reservation["allocations"])
            reservation["allocations"] = []; reservation["status"] = "RELEASED"
            if reservation["order_id"] is not None:
                order = self._data["orders"][reservation["order_id"]]
                if order["shipments"]:
                    raise ValueError("LOGISTICS_TRANSIT_RELEASE_REJECTED")
                order["cancelled_qty"] += qty; self._order_status(order)
            return {"released_qty": qty, **self._backfill(reservation["location"], reservation["sku"], day)}
        return self._apply("release:"+reservation_id, "RELEASE", day, {"reservation_id":reservation_id}, mutate)

    def place_order(self, orderid, source, dest, sku, qty, day, promised_day):
        identifier(orderid); self._location(source); self._location(dest); identifier(sku); integer(qty, 1);integer(day,0,100000); integer(promised_day, day, 100000)
        if source == dest or qty > self._capacity(dest):
            raise ValueError("LOGISTICS_ORDER_ROUTE_OR_CAPACITY_INVALID")
        def mutate(_):
            self._sku(sku)
            if orderid in self._data["orders"]:
                raise ValueError("LOGISTICS_ORDER_EXISTS")
            allocations, filled = self._fefo(source, sku, qty)
            if filled != qty:
                raise ValueError("LOGISTICS_ATP_INSUFFICIENT")
            rid = "order:"+orderid
            if rid in self._data["reservations"]:
                raise ValueError("LOGISTICS_RESERVATION_EXISTS")
            self._data["reservations"][rid] = {"reservation_id":rid,"location":source,"sku":sku,"qty":qty,
                "allocations":allocations,"status":"RESERVED","order_id":orderid}
            self._data["orders"][orderid] = {"order_id":orderid,"source":source,"dest":dest,"sku":sku,
                "ordered_qty":qty,"qty":qty,"placed_day":day,"promised_day":promised_day,"status":"PLACED",
                "dispatched_day":None,"departed_day":None,"received_day":None,"received_qty":0,"spoiled_qty":0,"cancelled_qty":0,"shipments":[]}
            return {"reserved_qty":qty,"open_incoming_qty":qty}
        return self._apply("order:"+orderid, "PLACE_ORDER", day, {"order_id":orderid,"source":source,"dest":dest,"sku":sku,"qty":qty,"promised_day":promised_day}, mutate)

    def dispatch(self, orderid, day):
        identifier(orderid)
        def mutate(_):
            if orderid not in self._data["orders"]:
                raise ValueError("LOGISTICS_ORDER_UNKNOWN")
            order=self._data["orders"][orderid];reservation=self._data["reservations"]["order:"+orderid]
            if order["status"] != "PLACED" or order["shipments"] or order["dispatched_day"] is not None:
                raise ValueError("LOGISTICS_ORDER_NOT_DISPATCHABLE")
            by_id={lot["lot_id"]:lot for lot in self._data["lots"]}
            for index, allocation in enumerate(reservation["allocations"]):
                lot=by_id[allocation["lot_id"]];lot["qty"]-=allocation["qty"]
                order["shipments"].append({"lot_id":key("transit:",[orderid,index]),"origin_lot_id":lot["lot_id"],
                    "qty":allocation["qty"],"created_day":lot["created_day"],"expiry_day":lot["expiry_day"]})
            reservation["allocations"]=[];reservation["status"]="DISPATCHED"
            self._data["lots"]=[lot for lot in self._data["lots"] if lot["qty"]]
            order["dispatched_day"]=order["departed_day"]=day;self._order_status(order)
            return {"shipped_qty":sum(lot["qty"] for lot in order["shipments"]),"spoiled_qty":order["spoiled_qty"]}
        return self._apply("dispatch:"+orderid,"DISPATCH",day,{"order_id":orderid},mutate)

    def receive(self, orderid, day):
        identifier(orderid)
        def mutate(_):
            if orderid not in self._data["orders"]:
                raise ValueError("LOGISTICS_ORDER_UNKNOWN")
            order=self._data["orders"][orderid]
            if order["dispatched_day"] is None or order["received_day"] is not None:
                raise ValueError("LOGISTICS_ORDER_NOT_RECEIVABLE")
            quantity=sum(lot["qty"] for lot in order["shipments"])
            if self._on_hand(order["dest"]) + quantity > self._capacity(order["dest"]):
                raise ValueError("LOGISTICS_CAPACITY_EXCEEDED")
            for lot in order["shipments"]:
                self._data["lots"].append({"lot_id":lot["lot_id"],"location":order["dest"],"sku":order["sku"],
                    "qty":lot["qty"],"created_day":lot["created_day"],"expiry_day":lot["expiry_day"]})
            order["shipments"]=[];order["received_qty"]+=quantity;order["received_day"]=day;self._order_status(order)
            return {"received_qty":quantity,"spoiled_qty":order["spoiled_qty"],"late_received_qty":quantity if day>order["promised_day"] else 0,
                    **self._backfill(order["dest"],order["sku"],day)}
        return self._apply("receive:"+orderid,"RECEIVE",day,{"order_id":orderid},mutate)

    def demand(self, location, sku, qty, day, mode="lost_sales", operation_id=None):
        self._location(location);identifier(sku);integer(qty)
        if mode not in ("lost_sales","backorder"):
            raise ValueError("LOGISTICS_DEMAND_MODE_INVALID")
        payload={"location":location,"sku":sku,"qty":qty,"mode":mode}
        operation_id=operation_id or key("demand:",[payload,day])
        def mutate(_):
            self._sku(sku)
            backfill=self._backfill(location,sku,day)
            allocations,filled=self._fefo(location,sku,qty,consume=True)
            missing=qty-filled;totals=self._data["totals"]
            totals["demanded"]+=qty;totals["fulfilled"]+=filled
            if mode=="backorder" and missing:
                self._data["backorders"].append({"backorder_id":operation_id,"location":location,"sku":sku,"qty":missing,"created_day":day})
                totals["backordered"]+=missing
            elif missing:
                totals["lost_sales"]+=missing
            return {"fulfilled":filled,"backordered":missing if mode=="backorder" else 0,
                    "lost_sales":missing if mode=="lost_sales" else 0,"allocations":allocations,**backfill}
        return self._apply(operation_id,"DEMAND",day,payload,mutate)

    def produce(self, location, sku, qty, day, operation_id=None):
        self._location(location);identifier(sku);integer(qty,1)
        payload={"location":location,"sku":sku,"qty":qty}
        operation_id=operation_id or key("produce:",[payload,day])
        def mutate(_):
            self._sku(sku)
            if self._on_hand(location)+qty>self._capacity(location):
                raise ValueError("LOGISTICS_CAPACITY_EXCEEDED")
            self._data["lots"].append({"lot_id":key("production:",operation_id),"location":location,"sku":sku,
                "qty":qty,"created_day":day,"expiry_day":day+self._data["production_shelf_life"]})
            self._data["totals"]["production"]+=qty
            return {"produced_qty":qty,**self._backfill(location,sku,day)}
        return self._apply(operation_id,"PRODUCE",day,payload,mutate)

    def expire(self, day, operation_id=None):
        return self._apply(operation_id or "expire:"+str(day),"EXPIRE",day,{},lambda expiry:expiry)

    def set_capacity(self, location, new_capacity, day, operation_id):
        self._location(location);integer(new_capacity)
        def mutate(_):
            if new_capacity<self._on_hand(location):
                raise ValueError("LOGISTICS_CAPACITY_BELOW_PHYSICAL_STOCK")
            before=self._capacity(location);self._data["capacities"][location]=new_capacity
            return {"previous_capacity":before,"capacity":new_capacity}
        return self._apply(operation_id,"SET_CAPACITY",day,{"location":location,"new_capacity":new_capacity},mutate)

    def set_shelf_life(self, days, day, operation_id):
        integer(days,1,3650)
        def mutate(_):
            before=self._data["production_shelf_life"];self._data["production_shelf_life"]=days
            return {"previous_shelf_life":before,"shelf_life":days,"scope":"FUTURE_PRODUCTION_ONLY"}
        return self._apply(operation_id,"SET_SHELF_LIFE",day,{"days":days},mutate)

    def summary(self):
        result={}
        for location,node in self.config["nodes"].items():
            result[location]={}
            for sku in self._data["skus"]:
                oh=self._on_hand(location,sku)
                reserved=sum(sum(a["qty"] for a in r["allocations"]) for r in self._data["reservations"].values() if r["location"]==location and r["sku"]==sku)
                incoming=transit=0
                for order in self._data["orders"].values():
                    if order["dest"]==location and order["sku"]==sku:
                        moving=sum(lot["qty"] for lot in order["shipments"])
                        transit+=moving
                        incoming+=moving+sum(a["qty"] for a in self._data["reservations"]["order:"+order["order_id"]]["allocations"])
                bo=sum(row["qty"] for row in self._data["backorders"] if row["location"]==location and row["sku"]==sku)
                result[location][sku]={"on_hand":oh,"reserved":reserved,"atp":oh-reserved,"on_order":incoming,
                    "in_transit":transit,"backorder":bo,"inventory_position":oh+incoming-bo,"capacity":self._capacity(location)}
        return {"schema_version":SCHEMA,"synthetic":True,"day":self._data["day"],"by_location":result,
                "global":self.verify_conservation(),"orders":deepcopy(list(self._data["orders"].values()))}

    def verify_conservation(self):
        data=self._data;integer(data["day"],self.config["initial_day"],100000)
        if not isinstance(data["skus"],list) or len(set(data["skus"]))!=len(data["skus"]) or len(data["skus"])>32:
            raise ValueError("LOGISTICS_SKU_STATE_INVALID")
        by_id={}
        for lot in data["lots"]:
            if set(lot)!={"lot_id","location","sku","qty","created_day","expiry_day"}:
                raise ValueError("LOGISTICS_LOT_FIELDS_INVALID")
            identifier(lot["lot_id"]);self._location(lot["location"]);integer(lot["qty"],1)
            integer(lot["created_day"],0,data["day"]);integer(lot["expiry_day"],data["day"]+1,103650)
            if lot["sku"] not in data["skus"] or lot["lot_id"] in by_id:
                raise ValueError("LOGISTICS_LOT_IDENTITY_INVALID")
            by_id[lot["lot_id"]]=lot
        reserved=self._reserved_by_lot()
        if any(lotid not in by_id or qty>by_id[lotid]["qty"] or qty<0 for lotid,qty in reserved.items()):
            raise ValueError("LOGISTICS_RESERVATION_CONSERVATION_INVALID")
        for rid,reservation in data["reservations"].items():
            fields={"reservation_id","location","sku","qty","allocations","status","order_id"}
            if not isinstance(reservation,dict) or set(reservation)!=fields or rid!=reservation["reservation_id"]:
                raise ValueError("LOGISTICS_RESERVATION_FIELDS_INVALID")
            self._location(reservation["location"]);integer(reservation["qty"],1)
            if reservation["sku"] not in data["skus"] or reservation["status"] not in ("RESERVED","DISPATCHED","RELEASED","SPOILED"):
                raise ValueError("LOGISTICS_RESERVATION_STATE_INVALID")
            if sum(a["qty"] for a in reservation["allocations"])>reservation["qty"]:
                raise ValueError("LOGISTICS_RESERVATION_QUANTITY_INVALID")
            for allocation in reservation["allocations"]:
                if set(allocation)!={"lot_id","qty"}:raise ValueError("LOGISTICS_RESERVATION_ALLOCATION_INVALID")
                integer(allocation["qty"],1)
                lot=by_id[allocation["lot_id"]]
                if lot["location"]!=reservation["location"] or lot["sku"]!=reservation["sku"]:
                    raise ValueError("LOGISTICS_RESERVATION_LOT_MISMATCH")
            if reservation["allocations"] and reservation["status"]!="RESERVED":
                raise ValueError("LOGISTICS_RESERVATION_STATUS_INVALID")
            if reservation["order_id"] is not None and (reservation["order_id"] not in data["orders"] or rid!="order:"+reservation["order_id"]):
                raise ValueError("LOGISTICS_RESERVATION_ORDER_MISMATCH")
        if set(data["capacities"])!=set(self.config["nodes"]):
            raise ValueError("LOGISTICS_CAPACITY_FIELDS_INVALID")
        integer(data["production_shelf_life"],1,3650)
        for location in self.config["nodes"]:
            integer(self._capacity(location))
            if self._on_hand(location)>self._capacity(location):
                raise ValueError("LOGISTICS_CAPACITY_EXCEEDED")
        transit=0;owned=set(by_id)
        for orderid,order in data["orders"].items():
            expected={"order_id","source","dest","sku","ordered_qty","qty","placed_day","promised_day","status","dispatched_day","departed_day","received_day","received_qty","spoiled_qty","cancelled_qty","shipments"}
            if set(order)!=expected or orderid!=order["order_id"] or "order:"+orderid not in data["reservations"]:
                raise ValueError("LOGISTICS_ORDER_FIELDS_INVALID")
            if order["qty"]!=order["ordered_qty"] or order["departed_day"]!=order["dispatched_day"]:
                raise ValueError("LOGISTICS_ORDER_ALIAS_MISMATCH")
            identifier(orderid)
            reservation=data["reservations"]["order:"+orderid]
            if (reservation["location"]!=order["source"] or reservation["sku"]!=order["sku"]
                    or reservation["order_id"]!=orderid or reservation["qty"]!=order["ordered_qty"]):
                raise ValueError("LOGISTICS_ORDER_RESERVATION_MISMATCH")
            self._location(order["source"]);self._location(order["dest"])
            integer(order["placed_day"],self.config["initial_day"],data["day"])
            integer(order["promised_day"],order["placed_day"],100000)
            if order["source"]==order["dest"] or order["sku"] not in data["skus"]:
                raise ValueError("LOGISTICS_ORDER_IDENTITY_INVALID")
            if order["dispatched_day"] is not None:integer(order["dispatched_day"],order["placed_day"],data["day"])
            if order["received_day"] is not None:
                if order["dispatched_day"] is None:raise ValueError("LOGISTICS_ORDER_RECEIVE_SEQUENCE_INVALID")
                integer(order["received_day"],order["dispatched_day"],data["day"])
            for lot in order["shipments"]:
                if set(lot)!={"lot_id","origin_lot_id","qty","created_day","expiry_day"} or lot["lot_id"] in owned:
                    raise ValueError("LOGISTICS_TRANSIT_OWNERSHIP_INVALID")
                integer(lot["qty"],1);integer(lot["expiry_day"],data["day"]+1,103650);owned.add(lot["lot_id"]);transit+=lot["qty"]
            incoming=sum(a["qty"] for a in data["reservations"]["order:"+orderid]["allocations"])+sum(lot["qty"] for lot in order["shipments"])
            for field in ("ordered_qty","received_qty","spoiled_qty","cancelled_qty"):
                integer(order[field])
            if order["ordered_qty"]!=incoming+order["received_qty"]+order["spoiled_qty"]+order["cancelled_qty"]:
                raise ValueError("LOGISTICS_ORDER_QUANTITY_CONSERVATION_INVALID")
            expected_status=("IN_TRANSIT" if order["shipments"] else "PLACED" if reservation["allocations"]
                else ("PARTIALLY_RECEIVED" if order["spoiled_qty"] or order["cancelled_qty"] else "RECEIVED") if order["received_qty"]
                else "CANCELLED" if order["cancelled_qty"] else "SPOILED")
            if order["status"]!=expected_status:
                raise ValueError("LOGISTICS_ORDER_STATUS_INVALID")
        totals=data["totals"]
        if set(totals)!={"initial","production","fulfilled","spoilage","spoiled","lost_sales","demanded","backordered"} or totals["spoiled"]!=totals["spoilage"]:
            raise ValueError("LOGISTICS_TOTAL_FIELDS_INVALID")
        for value in totals.values():integer(value,0,10**15)
        bo_ids=set()
        for row in data["backorders"]:
            if set(row)!={"backorder_id","location","sku","qty","created_day"} or row["backorder_id"] in bo_ids:
                raise ValueError("LOGISTICS_BACKORDER_FIELDS_INVALID")
            identifier(row["backorder_id"]);self._location(row["location"]);integer(row["qty"],1);integer(row["created_day"],self.config["initial_day"],data["day"])
            if row["sku"] not in data["skus"]:raise ValueError("LOGISTICS_BACKORDER_SKU_INVALID")
            bo_ids.add(row["backorder_id"])
        if [row["created_day"] for row in data["backorders"]]!=sorted(row["created_day"] for row in data["backorders"]):
            raise ValueError("LOGISTICS_BACKORDER_SEQUENCE_INVALID")
        initial=sum(sum(values.values()) for values in self.config["initial"].values())
        oh=sum(lot["qty"] for lot in data["lots"]);bo=sum(row["qty"] for row in data["backorders"])
        if totals["initial"]!=initial or oh+transit!=initial+totals["production"]-totals["fulfilled"]-totals["spoilage"]:
            raise ValueError("LOGISTICS_PHYSICAL_CONSERVATION_FAILED")
        if totals["demanded"]!=totals["fulfilled"]+totals["lost_sales"]+bo:
            raise ValueError("LOGISTICS_DEMAND_CONSERVATION_FAILED")
        return {"valid":True,**deepcopy(totals),"on_hand":oh,"in_transit":transit,"backorder":bo,
                "reserved":sum(reserved.values()),"physical_total":oh+transit,
                "physical_expected":initial+totals["production"]-totals["fulfilled"]-totals["spoilage"]}
