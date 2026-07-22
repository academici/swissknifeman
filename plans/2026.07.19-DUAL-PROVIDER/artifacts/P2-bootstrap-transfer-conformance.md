# P2.6 bootstrap-transfer conformance

All cases use `TemporaryDirectory` roots and hand-authored preimages/render results; no live root,
FOREMAN or fleet carrier is read or written.

| Case | Evidence | Expected result |
|:--|:--|:--|
| C1 exact D104 admission | exact two targets/IDs and recorded preimage | backup, two targets and one two-record lock; normal second plan is `noop` |
| C2 changed decision | `D105` descriptor | refuse; zero writes |
| C3 changed digest/path | altered digest or created path | refuse; zero writes |
| C4 changed-target race | preimage changed after plan | refuse before backup/lock write |
| C5 interrupted transaction | handler write raises | restore first preimage; no handler or lock remains |
| C6 ordinary drift repair | existing P2 regression suite | unchanged explicit-repair semantics |
| C7 retained records | existing P2 lock planner regression suite | ordinary retained-unexpected-record behavior remains unchanged |

Focused evidence: `PYTHONPATH=. python3 -m unittest discover -s core/tests -p 'test_provider_lock.py'`.
