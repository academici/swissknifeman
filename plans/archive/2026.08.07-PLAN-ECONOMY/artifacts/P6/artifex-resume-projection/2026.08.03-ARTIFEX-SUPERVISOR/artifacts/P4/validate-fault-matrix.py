#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
CUTS=["before_admission","after_admission","before_intent_append","after_intent_append","before_intent_reopen","after_intent_reopen","before_activity","after_activity","before_observation_append","after_observation_append","before_validation","after_validation","before_snapshot_replace","after_snapshot_replace","before_directory_fsync","after_directory_fsync"]
CONTRACTS=["supervisor-run-v1","slice-manifest-v1","authority-policy-v1","worker-envelope-v1","economy-evidence-v1","dispatch-admission-v1"]
def load(p):
 v=json.loads(Path(p).read_text()); 
 if not isinstance(v,dict): raise ValueError("object required")
 return v
p=argparse.ArgumentParser()
for n in ("matrix","cases","contracts","dispatch-contract","grant-index","admission-index","prototype","adapters","threats"): p.add_argument("--"+n,required=True)
a=p.parse_args()
try:
 for x in (a.contracts,a.grant_index,a.admission_index,a.prototype,a.adapters,a.threats): load(x)
 if not Path(a.dispatch_contract).is_file(): raise ValueError("dispatch contract")
 m,c=load(a.matrix),load(a.cases); ids=["F4-"+str(i).zfill(3) for i in range(1,17)]
 assert m["schema_version"]=="artifex-fault-matrix-v1" and m["contracts"]==CONTRACTS and m["cuts"]==CUTS
 assert [r["id"] for r in m["rows"]]==ids and [r["cut_id"] for r in m["rows"]]==CUTS
 assert all(r["setup"]=="fresh-child" and r["trigger"]=="deterministic-crash" and r["evidence_class"]=="child-process" for r in m["rows"])
 assert c["schema_version"]=="artifex-fault-cases-v1" and [r["id"] for r in c["cases"]]==ids and all(r["expected_exit"]==97 and r["positive_reachability"] is True for r in c["cases"])
 print("fault matrix validator: OK (16 child-process cuts; six contracts)")
except (AssertionError,KeyError,ValueError,TypeError,json.JSONDecodeError) as e:
 print("fault matrix validator: FAIL: "+str(e),file=sys.stderr); raise SystemExit(1)

