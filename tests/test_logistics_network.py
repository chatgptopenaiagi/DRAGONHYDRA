"""Route/capacity and complete virtual cost accounting tests."""
from copy import deepcopy
import unittest

from dragonhydra.cognitive_logistics.network import Network
from dragonhydra.cognitive_logistics.costs import CostLedger,COMPONENTS


def graph():
    return {'nodes':{x:{'kind':'warehouse','capacity':100} for x in ('a','b','c','d','e')},'edges':[
        {'id':'ab','source':'a','dest':'b','distance':1,'unit_cost':5,'lead_time':2,'reliability':.99,'capacity':5},
        {'id':'bd','source':'b','dest':'d','distance':1,'unit_cost':5,'lead_time':2,'reliability':.99,'capacity':5},
        {'id':'ac','source':'a','dest':'c','distance':5,'unit_cost':1,'lead_time':1,'reliability':.5,'capacity':8},
        {'id':'cd','source':'c','dest':'d','distance':5,'unit_cost':1,'lead_time':1,'reliability':.5,'capacity':8}]}


class NetworkTests(unittest.TestCase):
    def test_metrics_choose_actual_different_routes(self):
        network=Network(graph())
        self.assertEqual(network.shortest_path('a','d','distance')['nodes'],['a','b','d'])
        self.assertEqual(network.shortest_path('a','d','cost')['nodes'],['a','c','d'])
        self.assertEqual(network.shortest_path('a','d','time')['lead_time'],2)
        best=network.shortest_path('a','d','reliability')
        self.assertEqual(best['nodes'],['a','b','d']);self.assertAlmostEqual(best['reliability'],.9801)
        self.assertEqual(network.shortest_path('a','d','cost_reliability',reliability_penalty=10)['nodes'],['a','b','d'])
        self.assertEqual(network.shortest_path('a','d','cost_reliability',reliability_penalty=0)['nodes'],['a','c','d'])

    def test_connectivity_is_directed_and_capacity_aware(self):
        network=Network(graph())
        self.assertIsNone(network.shortest_path('d','a'))
        self.assertFalse(network.connected('a','e'))
        self.assertEqual(network.shortest_path('a','d','cost',{'ac':8})['edge_ids'],['ab','bd'])
        self.assertIsNone(network.shortest_path('a','d','cost',{'ac':8,'ab':5}))
        with self.assertRaises(ValueError):network.shortest_path('unknown','d')

    def test_allocation_respects_residual_capacities_and_reports_unallocated(self):
        network=Network(graph());sources={'a':20};usage={};before=deepcopy(sources)
        plan=network.allocate(sources,'d',20,edge_usage=usage)
        self.assertEqual((plan['allocated'],plan['unallocated']),(13,7))
        self.assertEqual([row['qty'] for row in plan['allocations']],[8,5])
        self.assertEqual(plan['edge_usage'],{'ab':5,'bd':5,'ac':8,'cd':8})
        self.assertEqual(sources,before);self.assertEqual(usage,{})

    def test_multiple_suppliers_select_cheaper_stock_then_next_source(self):
        raw=graph();raw['edges']=[
            {'id':'ad','source':'a','dest':'d','capacity':10,'unit_cost':2},
            {'id':'bd','source':'b','dest':'d','capacity':10,'unit_cost':1}]
        plan=Network(raw).allocate({'a':8,'b':8},'d',10)
        self.assertEqual([(x['source'],x['qty']) for x in plan['allocations']],[('b',8),('a',2)])

    def test_zero_cost_cycle_still_returns_bounded_simple_path(self):
        raw=graph();raw['edges'] += [{'id':'ba','source':'b','dest':'a','capacity':10,'unit_cost':0}]
        path=Network(raw).shortest_path('a','d','cost')
        self.assertEqual(len(path['nodes']),len(set(path['nodes'])))

    def test_explicit_network_intervention_does_not_mutate_original(self):
        network=Network(graph());changed=network.to_dict();changed['edges'][2]['capacity']=0
        self.assertEqual(Network(changed).shortest_path('a','d','cost')['nodes'],['a','b','d'])
        self.assertEqual(network.shortest_path('a','d','cost')['nodes'],['a','c','d'])
        self.assertEqual(Network.from_dict(network.to_dict()).to_dict(),network.to_dict())

    def test_invalid_edges_numbers_and_usage_are_rejected(self):
        for field,value in (('unit_cost',-1),('distance',float('nan')),('reliability',0),('reliability',float('inf')),('capacity',True),('lead_time',1.5)):
            raw=graph();raw['edges'][0][field]=value
            with self.assertRaises(ValueError):Network(raw)
        with self.assertRaises(ValueError):Network(graph()).allocate({'a':1},'d',-1)
        with self.assertRaises(ValueError):Network(graph()).shortest_path('a','d',edge_usage={'ab':6})
        with self.assertRaises(ValueError):Network(graph()).shortest_path('a','d','weighted',weights={'bad':1})


class CostLedgerTests(unittest.TestCase):
    def test_all_seven_components_and_total_are_present(self):
        ledger=CostLedger()
        self.assertTrue(set(COMPONENTS)<=ledger.summary().keys())
        self.assertEqual(ledger.summary()['total'],0)
        for index,component in enumerate(COMPONENTS,1):ledger.record('c'+str(index),component,index,28)
        self.assertEqual(ledger.summary()['total'],28)

    def test_charge_records_exact_quantity_and_unit_rate(self):
        ledger=CostLedger({'holding':.25})
        row=ledger.charge('holding-day28','holding',4,28)
        self.assertEqual(row['amount'],1)
        self.assertEqual(row['metadata'],{'quantity':4.,'unit_rate':.25})

    def test_idempotence_conflicts_and_roundtrip(self):
        ledger=CostLedger();row=ledger.record('x','ordering',2,28)
        self.assertEqual(ledger.record('x','ordering',2,28),row)
        with self.assertRaises(ValueError):ledger.record('x','ordering',3,28)
        self.assertEqual(ledger.summary()['record_count'],1)
        copy=CostLedger.from_dict(ledger.to_dict())
        self.assertEqual(copy.to_dict(),ledger.to_dict())
        self.assertEqual(copy.record('x','ordering',2,28),row)

    def test_negative_nonfinite_unknown_and_duplicate_records_rejected(self):
        ledger=CostLedger()
        for amount in (-1,True,float('nan'),float('inf'),10**1000):
            with self.assertRaises(ValueError):ledger.record('x','transport',amount)
        with self.assertRaises(ValueError):ledger.record('x','untracked_fee',1)
        ledger.record('x','transport',1)
        raw=ledger.to_dict();raw['records'].append(deepcopy(raw['records'][0]))
        with self.assertRaises(ValueError):CostLedger.from_dict(raw)


if __name__=='__main__':unittest.main()
