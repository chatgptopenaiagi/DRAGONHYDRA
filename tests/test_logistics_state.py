"""Physical inventory identities on disposable invented stock and routes."""
from copy import deepcopy
import unittest

from dragonhydra.cognitive_logistics.state import InventoryState


def config(source=30,retail=2,capacity=20,shelf=14,initial_day=0):
    return {"nodes":{"s":{"kind":"supplier","capacity":100},"r":{"kind":"retail","capacity":capacity}},
            "initial":{"s":{"SKU":source},"r":{"SKU":retail}},"shelf_life":shelf,"initial_day":initial_day}


class InventoryTests(unittest.TestCase):
    def test_order_transit_not_counted_twice_in_inventory_position(self):
        state=InventoryState(config())
        state.place_order('o','s','r','SKU',10,0,2)
        before=state.summary()['by_location']['r']['SKU']
        self.assertEqual((before['on_hand'],before['on_order'],before['in_transit'],before['inventory_position']),(2,10,0,12))
        state.dispatch('o',0)
        during=state.summary()['by_location']['r']['SKU']
        self.assertEqual((during['on_order'],during['in_transit'],during['inventory_position']),(10,10,12))
        self.assertEqual(state.verify_conservation()['physical_total'],32)
        state.receive('o',2)
        after=state.summary()['by_location']['r']['SKU']
        self.assertEqual((after['on_hand'],after['on_order'],after['in_transit'],after['inventory_position']),(12,0,0,12))
        self.assertEqual(state.to_dict()['orders']['o']['departed_day'],0)

    def test_reservations_protect_stock_from_demand_and_release_once(self):
        state=InventoryState(config(source=10,retail=0))
        state.reserve('held','s','SKU',7,0)
        result=state.demand('s','SKU',8,0,operation_id='d1')
        self.assertEqual((result['fulfilled'],result['lost_sales']),(3,5))
        row=state.summary()['by_location']['s']['SKU']
        self.assertEqual((row['on_hand'],row['reserved'],row['atp']),(7,7,0))
        state.release('held',0)
        state.demand('s','SKU',7,0,operation_id='d2')
        self.assertEqual(state.verify_conservation()['physical_total'],0)
        self.assertEqual(state.verify_conservation()['fulfilled'],10)

    def test_fefo_uses_earliest_expiry_and_keeps_fresher_lot(self):
        state=InventoryState(config(source=5,retail=0,shelf=3))
        state.produce('s','SKU',4,1,operation_id='p')
        initial=next(lot['lot_id'] for lot in state.to_dict()['lots'] if lot['created_day']==0)
        receipt=state.demand('s','SKU',5,1,operation_id='d')
        self.assertEqual(receipt['allocations'],[{'lot_id':initial,'qty':5}])
        self.assertEqual(state.expire(3)['expired_qty'],0)
        self.assertEqual(state.summary()['by_location']['s']['SKU']['on_hand'],4)

    def test_backorders_are_oldest_first_and_late_fulfillment_is_conserved(self):
        state=InventoryState(config(source=0,retail=0))
        state.demand('r','SKU',5,0,'backorder',operation_id='first')
        state.demand('r','SKU',5,1,'backorder',operation_id='second')
        self.assertEqual(state.summary()['by_location']['r']['SKU']['inventory_position'],-10)
        receipt=state.produce('r','SKU',7,2,operation_id='production')
        self.assertEqual((receipt['fulfilled_backorders'],receipt['late_fulfilled']),(7,7))
        self.assertEqual([(x['backorder_id'],x['qty']) for x in state.to_dict()['backorders']],[('second',3)])
        totals=state.verify_conservation()
        self.assertEqual((totals['production'],totals['fulfilled'],totals['physical_total'],totals['backorder']),(7,7,0,3))

    def test_receive_backfills_but_capacity_precedes_implicit_crossdock(self):
        state=InventoryState(config(source=20,retail=9,capacity=10))
        state.reserve('held','r','SKU',9,0)
        state.demand('r','SKU',5,0,'backorder',operation_id='d')
        state.place_order('o','s','r','SKU',5,0,1);state.dispatch('o',0)
        before=state.to_dict()
        with self.assertRaisesRegex(ValueError,'CAPACITY'):
            state.receive('o',1)
        self.assertEqual(state.to_dict(),before)
        release=state.release('held',1)
        self.assertEqual(release['fulfilled_backorders'],5)
        state.receive('o',1)
        self.assertEqual(state.summary()['by_location']['r']['SKU']['on_hand'],9)

    def test_receive_reports_late_delivery_and_clears_backorders(self):
        state=InventoryState(config(source=20,retail=0))
        state.demand('r','SKU',6,0,'backorder',operation_id='d')
        state.place_order('o','s','r','SKU',10,0,1);state.dispatch('o',0)
        receipt=state.receive('o',2)
        self.assertEqual((receipt['received_qty'],receipt['late_received_qty'],receipt['fulfilled_backorders'],receipt['late_fulfilled']),(10,10,6,6))
        self.assertEqual(state.summary()['by_location']['r']['SKU']['on_hand'],4)

    def test_transit_and_on_hand_expiry_destroy_units_without_resurrection(self):
        state=InventoryState(config(source=10,retail=0,shelf=2))
        state.place_order('o','s','r','SKU',5,0,3);state.dispatch('o',0)
        receipt=state.expire(2)
        self.assertEqual((receipt['expired_on_hand'],receipt['expired_in_transit'],receipt['expired_qty']),(5,5,10))
        self.assertEqual(state.to_dict()['orders']['o']['status'],'SPOILED')
        self.assertEqual(state.summary()['by_location']['r']['SKU']['on_order'],0)
        self.assertEqual(state.receive('o',3)['received_qty'],0)
        self.assertEqual(state.verify_conservation()['physical_total'],0)
        self.assertEqual(state.verify_conservation()['spoiled'],10)

    def test_expired_reserved_fraction_reduces_only_its_order_open_units(self):
        state=InventoryState(config(source=5,retail=0,shelf=2))
        state.produce('s','SKU',5,1,operation_id='p')
        state.place_order('o','s','r','SKU',8,1,2)
        state.expire(2)
        self.assertEqual(state.summary()['by_location']['r']['SKU']['on_order'],3)
        self.assertEqual(state.dispatch('o',2)['shipped_qty'],3)
        self.assertEqual(state.receive('o',2)['received_qty'],3)
        self.assertEqual(state.to_dict()['orders']['o']['status'],'PARTIALLY_RECEIVED')
        self.assertEqual(state.verify_conservation()['physical_total'],5)

    def test_automatic_expiry_prevents_consuming_past_shelf_life(self):
        state=InventoryState(config(source=5,retail=0,shelf=1))
        receipt=state.demand('s','SKU',3,1,operation_id='d')
        self.assertEqual((receipt['fulfilled'],receipt['lost_sales'],receipt['automatic_spoilage_qty']),(0,3,5))

    def test_idempotence_returns_original_receipt_and_conflicts_abort(self):
        state=InventoryState(config())
        receipt=state.place_order('o','s','r','SKU',5,0,2)
        self.assertEqual(state.place_order('o','s','r','SKU',5,0,2),receipt)
        self.assertEqual(len(state.to_dict()['events']),1)
        before=state.to_dict()
        with self.assertRaisesRegex(ValueError,'CONFLICT'):
            state.place_order('o','s','r','SKU',6,0,2)
        self.assertEqual(state.to_dict(),before)
        demand=state.demand('r','SKU',1,0,operation_id='d')
        self.assertEqual(state.demand('r','SKU',1,0,operation_id='d'),demand)

    def test_roundtrip_preserves_idempotence_and_future_arrival_is_forbidden(self):
        state=InventoryState(config(initial_day=28))
        receipt=state.place_order('o','s','r','SKU',5,28,30);state.dispatch('o',28)
        raw=state.to_dict();copy=InventoryState.from_dict(raw)
        self.assertEqual(copy.to_dict(),raw)
        self.assertEqual(copy.place_order('o','s','r','SKU',5,28,30),receipt)
        raw['orders']['o']['actual_arrival_day']=31
        with self.assertRaises(ValueError):InventoryState.from_dict(raw)

    def test_interventions_change_capacity_or_future_production_only(self):
        state=InventoryState(config(source=5,retail=0,shelf=14))
        expiry=state.to_dict()['lots'][0]['expiry_day']
        state.set_shelf_life(2,0,'shelf-change');state.produce('s','SKU',1,0,operation_id='p')
        self.assertEqual(sorted(lot['expiry_day'] for lot in state.to_dict()['lots']),[2,expiry])
        before=state.to_dict()
        with self.assertRaises(ValueError):state.set_capacity('s',5,0,'capacity-too-small')
        self.assertEqual(state.to_dict(),before)
        state.demand('s','SKU',5,0,operation_id='d')
        state.set_capacity('s',1,0,'capacity-reduce')
        self.assertEqual(InventoryState.from_dict(state.to_dict()).summary()['by_location']['s']['SKU']['capacity'],1)

    def test_invalid_quantities_capacity_clock_and_order_sequence_are_rejected(self):
        state=InventoryState(config())
        for quantity in (-1,True,1.5,float('nan'),10**1000):
            with self.assertRaises(ValueError):state.produce('s','SKU',quantity,0,operation_id='invalid')
        with self.assertRaises(ValueError):state.produce('r','SKU',30,0,operation_id='over-capacity')
        state.place_order('o','s','r','SKU',5,0,2)
        before=state.to_dict()
        with self.assertRaises(ValueError):state.receive('o',1)
        self.assertEqual(state.to_dict(),before)
        state.expire(1)
        with self.assertRaises(ValueError):state.demand('s','SKU',1,0,operation_id='rewind')
        with self.assertRaises(ValueError):state.place_order('self','s','s','SKU',1,1,2)

    def test_tampered_physical_units_and_negative_backorders_are_rejected(self):
        state=InventoryState(config(source=0,retail=0))
        state.demand('r','SKU',3,0,'backorder',operation_id='d')
        raw=state.to_dict();raw['backorders'][0]['qty']=-3
        with self.assertRaises(ValueError):InventoryState.from_dict(raw)
        raw=InventoryState(config()).to_dict();raw['lots'][0]['qty']+=1
        with self.assertRaises(ValueError):InventoryState.from_dict(raw)

    def test_returned_snapshots_do_not_alias_owned_state(self):
        state=InventoryState(config());raw=state.to_dict();summary=state.summary()
        raw['lots'][0]['qty']=999;summary['by_location']['r']['SKU']['on_hand']=999
        self.assertEqual(state.summary()['by_location']['r']['SKU']['on_hand'],2)

    def test_order_cannot_overwrite_existing_general_reservation(self):
        state=InventoryState(config())
        state.reserve('order:o','s','SKU',8,0)
        before=state.to_dict()
        with self.assertRaises(ValueError):state.place_order('o','s','r','SKU',5,0,2)
        self.assertEqual(state.to_dict(),before)

    def test_deserialization_rejects_wrong_transit_status_and_source_ownership(self):
        state=InventoryState(config());state.place_order('o','s','r','SKU',5,0,2);state.dispatch('o',0)
        raw=state.to_dict();raw['orders']['o']['status']='PLACED'
        with self.assertRaises(ValueError):InventoryState.from_dict(raw)
        raw=state.to_dict();raw['orders']['o']['source']='r'
        with self.assertRaises(ValueError):InventoryState.from_dict(raw)


if __name__=='__main__':unittest.main()
