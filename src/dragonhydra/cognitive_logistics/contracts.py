"""Domain-specific visibility and identity contracts. All units are fictional."""
from __future__ import annotations
import hashlib,json,math,re

SKU='SKU_VIRTUAL_1'
LOCATIONS=('retail_a','retail_b')
FAMILIES=('stable','intermittent','seasonal','supplier_disruption','perishable','multi_location')
TRAIN_FAMILIES=('stable','intermittent')
VALIDATION_FAMILIES=('seasonal',)
UNSEEN_FAMILIES=('supplier_disruption','perishable','multi_location')
CATEGORIES=('demand_signal','supplier_status','carrier_queue','downstream_intent')
POLICIES=('reorder_point','order_up_to','base_stock','s_S','probabilistic_cost')
ACQUISITIONS=('none','all','random','handcrafted','learned')
COST_KEYS=('holding','ordering','shortage','transport','spoilage','acquisition','computation')

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def identity(prefix,value):return 'virtual-'+prefix+'-'+digest(value)[:28]
def integer(value,low=0,high=1000000):
    if type(value) is not int or not low<=value<=high:raise ValueError('LOGISTICS_INTEGER_OUT_OF_BOUNDS')
    return value
def finite(value,low=0,high=1000000):
    if type(value) not in (int,float) or not low<=value<=high or not math.isfinite(value):raise ValueError('LOGISTICS_NUMBER_OUT_OF_BOUNDS')
    return float(value)
def request_id(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',value):raise ValueError('LOGISTICS_REQUEST_ID_INVALID')
    return value
def cost_difference(before,after):
    return {key:finite(after.get(key,0),0,1e12)-finite(before.get(key,0),0,1e12) for key in COST_KEYS}
def visible_evidence(snapshot):
    day=integer(snapshot['day'],0,100000)
    acquired=snapshot.get('acquired')
    if not isinstance(acquired,dict) or set(acquired)-set(CATEGORIES):raise ValueError('LOGISTICS_ACQUIRED_SCHEMA_INVALID')
    result={}
    for category,row in acquired.items():
        if not isinstance(row,dict) or row.get('category')!=category or row.get('synthetic') is not True:raise ValueError('LOGISTICS_ACQUIRED_IDENTITY_INVALID')
        observed=integer(row['observed_day'],0,100000);available=integer(row['available_day'],0,100000);received=integer(row['received_day'],0,100000)
        if not observed<=available<=received<=day:raise ValueError('LOGISTICS_OBSERVATION_TIME_LEAKAGE')
        value=row['value']
        if not isinstance(value,dict):raise ValueError('LOGISTICS_OBSERVATION_VALUE_INVALID')
        if category in ('demand_signal','downstream_intent'):
            if set(value)!=set(LOCATIONS):raise ValueError('LOGISTICS_OBSERVATION_VALUE_INVALID')
            for number in value.values():finite(number,0,1)
        elif category=='supplier_status':
            if set(value)!={'delay_band'} or value['delay_band'] not in ('NORMAL','CONGESTED'):raise ValueError('LOGISTICS_OBSERVATION_VALUE_INVALID')
        elif set(value)!={'queue_days'}:raise ValueError('LOGISTICS_OBSERVATION_VALUE_INVALID')
        else:integer(value['queue_days'],0,5)
        if day-observed<=2:result[category]=row
    return result
