"""Complete nonnegative virtual-credit cost ledger; no real payments."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math

from .state import canonical,identifier,integer

COMPONENTS=("holding","ordering","shortage","transport","spoilage","acquisition","computation")
DEFAULT_RATES={"holding":.01,"ordering":1.,"shortage":2.,"transport":.1,"spoilage":1.,"acquisition":.02,"computation":.001}


def finite(value,low=0,high=10**15):
    if type(value) not in (int,float) or not low<=value<=high or not math.isfinite(value):
        raise ValueError("LOGISTICS_COST_NUMBER_INVALID")
    return float(value) if value else 0.0


class CostLedger:
    def __init__(self,rates=None):
        if rates is not None and (not isinstance(rates,dict) or set(rates)-set(COMPONENTS)):
            raise ValueError("LOGISTICS_COST_RATES_INVALID")
        self.rates={key:finite((rates or {}).get(key,DEFAULT_RATES[key])) for key in COMPONENTS}
        self._records=[];self._operations={}

    def record(self,operation_id,component,amount,day=0,metadata=None):
        identifier(operation_id);integer(day,0,100000)
        if component not in COMPONENTS:raise ValueError("LOGISTICS_COST_COMPONENT_INVALID")
        amount=finite(amount)
        if metadata is not None and not isinstance(metadata,dict):raise ValueError("LOGISTICS_COST_METADATA_INVALID")
        metadata=deepcopy(metadata or {})
        if len(canonical(metadata).encode())>8192:raise ValueError("LOGISTICS_COST_METADATA_LIMIT")
        payload={"component":component,"amount":amount,"day":day,"metadata":metadata}
        fingerprint=hashlib.sha256(canonical(payload).encode()).hexdigest()
        if operation_id in self._operations:
            old=self._operations[operation_id]
            if old["fingerprint"]!=fingerprint:raise ValueError("LOGISTICS_COST_ID_CONFLICT")
            return deepcopy(self._records[old["index"]])
        if len(self._records)>=100000:raise ValueError("LOGISTICS_COST_RECORD_LIMIT")
        row={"schema_version":"dragonhydra.logistics-cost/1","synthetic":True,"cost_id":operation_id,
             "cost_unit":"VIRTUAL_CREDIT",**payload}
        self._operations[operation_id]={"fingerprint":fingerprint,"index":len(self._records)}
        self._records.append(row)
        return deepcopy(row)

    def charge(self,operation_id,component,quantity=1,day=0,unit_rate=None,metadata=None):
        if component not in COMPONENTS:raise ValueError("LOGISTICS_COST_COMPONENT_INVALID")
        quantity=finite(quantity);rate=self.rates[component] if unit_rate is None else finite(unit_rate)
        return self.record(operation_id,component,finite(quantity*rate),day,
                           {**(metadata or {}),"quantity":quantity,"unit_rate":rate})

    def summary(self):
        result={name:math.fsum(row["amount"] for row in self._records if row["component"]==name) for name in COMPONENTS}
        return {**result,"total":math.fsum(result.values()),"record_count":len(self._records),"cost_unit":"VIRTUAL_CREDIT"}

    def to_dict(self):
        return {"schema_version":"dragonhydra.logistics-cost-ledger/1","rates":deepcopy(self.rates),"records":deepcopy(self._records)}

    @classmethod
    def from_dict(cls,raw):
        if not isinstance(raw,dict) or set(raw)!={"schema_version","rates","records"} or raw["schema_version"]!="dragonhydra.logistics-cost-ledger/1" or not isinstance(raw["records"],list):
            raise ValueError("LOGISTICS_COST_LEDGER_SCHEMA_INVALID")
        result=cls(raw["rates"])
        for row in raw["records"]:
            if not isinstance(row,dict) or set(row)!={"schema_version","synthetic","cost_id","cost_unit","component","amount","day","metadata"} or row["synthetic"] is not True or row["schema_version"]!="dragonhydra.logistics-cost/1" or row["cost_unit"]!="VIRTUAL_CREDIT":
                raise ValueError("LOGISTICS_COST_RECORD_SCHEMA_INVALID")
            if row["cost_id"] in result._operations:raise ValueError("LOGISTICS_COST_DUPLICATE_RECORD")
            result.record(row["cost_id"],row["component"],row["amount"],row["day"],row["metadata"])
        return result
