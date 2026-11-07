"""Bounded directed logistics graph; deterministic paths and feasible allocation."""
from __future__ import annotations

from copy import deepcopy
import heapq
import math

from .state import identifier, integer


def finite(value, low=0, high=10**12):
    if type(value) not in (int,float) or not low<=value<=high or not math.isfinite(value):
        raise ValueError("LOGISTICS_NETWORK_NUMBER_INVALID")
    return float(value)


class Network:
    def __init__(self, config):
        if not isinstance(config,dict) or set(config)-{"nodes","edges"}:
            raise ValueError("LOGISTICS_NETWORK_CONFIG_INVALID")
        nodes=config.get("nodes");edges=config.get("edges")
        if not isinstance(nodes,dict) or not 1<=len(nodes)<=32 or not isinstance(edges,list) or len(edges)>256:
            raise ValueError("LOGISTICS_NETWORK_BOUNDS")
        self.nodes={}
        for name,node in nodes.items():
            identifier(name)
            if not isinstance(node,dict) or set(node)!={"kind","capacity"}:
                raise ValueError("LOGISTICS_NETWORK_NODE_INVALID")
            self.nodes[name]={"kind":identifier(node["kind"]),"capacity":integer(node["capacity"])}
        self.edges={};self._adj={node:[] for node in nodes}
        for index,raw in enumerate(edges):
            if not isinstance(raw,dict) or set(raw)-{"id","source","dest","distance","lead_time","unit_cost","reliability","capacity"}:
                raise ValueError("LOGISTICS_NETWORK_EDGE_INVALID")
            source,dest=raw.get("source"),raw.get("dest")
            if source not in nodes or dest not in nodes or source==dest:
                raise ValueError("LOGISTICS_NETWORK_ENDPOINT_INVALID")
            eid=identifier(raw.get("id","edge:"+source+":"+dest+":"+str(index)))
            if eid in self.edges:
                raise ValueError("LOGISTICS_NETWORK_EDGE_DUPLICATE")
            reliability=finite(raw.get("reliability",1),0,1)
            if not reliability:
                raise ValueError("LOGISTICS_NETWORK_RELIABILITY_INVALID")
            edge={"id":eid,"source":source,"dest":dest,"distance":finite(raw.get("distance",0)),
                  "lead_time":integer(raw.get("lead_time",0),0,3650),"unit_cost":finite(raw.get("unit_cost",0)),
                  "reliability":reliability,"capacity":integer(raw.get("capacity",0))}
            self.edges[eid]=edge;self._adj[source].append(eid)
        for row in self._adj.values():row.sort()

    def to_dict(self):
        return {"nodes":deepcopy(self.nodes),"edges":deepcopy(list(self.edges.values()))}

    @classmethod
    def from_dict(cls, raw):
        return cls(raw)

    def _usage(self, usage):
        if usage is None:return {edge:0 for edge in self.edges}
        if not isinstance(usage,dict) or set(usage)-set(self.edges):
            raise ValueError("LOGISTICS_NETWORK_USAGE_INVALID")
        return {eid:integer(usage.get(eid,0),0,edge["capacity"]) for eid,edge in self.edges.items()}

    def shortest_path(self, source, dest, metric="distance", edge_usage=None, weights=None, reliability_penalty=1.0):
        if source not in self.nodes or dest not in self.nodes:
            raise ValueError("LOGISTICS_NETWORK_NODE_UNKNOWN")
        metric={"mincost":"cost","mintime":"time"}.get(metric,metric)
        if metric not in ("distance","cost","time","reliability","weighted","cost_reliability"):
            raise ValueError("LOGISTICS_NETWORK_METRIC_INVALID")
        if weights is not None and (not isinstance(weights,dict) or set(weights)-{"distance","cost","time","risk"}):
            raise ValueError("LOGISTICS_NETWORK_WEIGHTS_INVALID")
        factors={name:finite((weights or {}).get(name,1)) for name in ("distance","cost","time","risk")}
        if metric=="weighted" and not sum(factors.values()):
            raise ValueError("LOGISTICS_NETWORK_WEIGHTS_EMPTY")
        usage=self._usage(edge_usage)
        reliability_penalty=finite(reliability_penalty,0,10**6)
        def weight(edge):
            values={"distance":edge["distance"],"cost":edge["unit_cost"],"time":edge["lead_time"],"risk":-math.log(edge["reliability"])}
            if metric=="cost_reliability":return values["cost"]+reliability_penalty*values["risk"]
            return sum(values[name]*factors[name] for name in factors) if metric=="weighted" else values["risk" if metric=="reliability" else metric]
        queue=[(0.,(source,),(),source)];best={source:0.};settled=set()
        while queue:
            score,nodes,edges,node=heapq.heappop(queue)
            if node in settled:continue
            settled.add(node)
            if node==dest:
                selected=[self.edges[eid] for eid in edges]
                return {"nodes":list(nodes),"edge_ids":list(edges),"distance":sum(e["distance"] for e in selected),
                        "lead_time":sum(e["lead_time"] for e in selected),"unit_cost":sum(e["unit_cost"] for e in selected),
                        "reliability":math.prod(e["reliability"] for e in selected),
                        "capacity":min((e["capacity"]-usage[e["id"]] for e in selected),default=self.nodes[source]["capacity"]),
                        "metric":metric,"objective":score,"reliability_penalty":reliability_penalty,
                        "lead_time_scope":"DECLARED_PROMISE_NOT_ACTUAL_ARRIVAL"}
            for eid in self._adj[node]:
                edge=self.edges[eid];target=edge["dest"]
                if target in nodes or edge["capacity"]<=usage[eid]:continue
                candidate=score+weight(edge)
                if candidate<=best.get(target,float('inf')):
                    best[target]=candidate;heapq.heappush(queue,(candidate,nodes+(target,),edges+(eid,),target))
        return None

    def connected(self,source,dest):
        return self.shortest_path(source,dest) is not None

    def allocate(self,sources,dest,qty,metric="cost",edge_usage=None,reliability_penalty=1.0):
        if not isinstance(sources,dict) or len(sources)>32 or dest not in self.nodes:
            raise ValueError("LOGISTICS_NETWORK_ALLOCATION_INVALID")
        available={name:integer(value) for name,value in sources.items()}
        if set(available)-set(self.nodes):raise ValueError("LOGISTICS_NETWORK_NODE_UNKNOWN")
        requested=integer(qty);remaining=requested;usage=self._usage(edge_usage);allocations=[]
        for _ in range(len(self.edges)+len(available)+1):
            if not remaining:break
            choices=[]
            for source,quantity in available.items():
                if not quantity or source==dest:continue
                path=self.shortest_path(source,dest,metric,usage,reliability_penalty=reliability_penalty)
                if path is not None and path["capacity"]:
                    choices.append((path["objective"],source,tuple(path["edge_ids"]),path))
            if not choices:break
            _,source,_,path=min(choices,key=lambda row:row[:3])
            quantity=min(remaining,available[source],path["capacity"])
            if quantity<=0:raise ValueError("LOGISTICS_NETWORK_ALLOCATION_STALLED")
            for eid in path["edge_ids"]:usage[eid]+=quantity
            available[source]-=quantity;remaining-=quantity
            allocations.append({"source":source,"dest":dest,"qty":quantity,"path":path})
        else:
            raise ValueError("LOGISTICS_NETWORK_ALLOCATION_BOUND_EXCEEDED")
        return {"schema_version":"dragonhydra.logistics-allocation/1","synthetic":True,"requested":requested,
                "allocated":requested-remaining,"unallocated":remaining,"allocations":allocations,"edge_usage":usage,
                "method":"BOUNDED_GREEDY_RESIDUAL_PATHS_NOT_GLOBAL_FLOW_OR_VRP_OPTIMUM"}


GraphNetwork=Network
