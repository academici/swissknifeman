#!/usr/bin/env python3
"""Пере-агрегация churn файл-операций (P2.1) — категоризация tool_failures[].snippet
по паттернам (not-read-first / string-not-found / not-unique / deny-permission / прочее)
+ сумма reads.top_rereads. Окно/фильтр — те же, что в agg.py (-mtime -4,
*/.claude/runs/*.json), иначе числа с baseline несопоставимы."""
import json, subprocess, collections, re

out = subprocess.run(
    ["find", "/home/vostrikov", "-path", "*/.claude/runs/*.json", "-type", "f", "-mtime", "-4"],
    capture_output=True, text=True).stdout
files = [f for f in out.splitlines() if f]

NOT_READ_FIRST = re.compile(r"has not been read yet", re.I)
STRING_NOT_FOUND = re.compile(r"string to replace not found", re.I)
NOT_UNIQUE = re.compile(r"matches of the string to replace, but replace_all is false", re.I)
DENY_RULE = re.compile(r"covered by a .* deny rule|permission settings and cannot be", re.I)


def proj(f):
    return f.split('/.claude/runs/')[0].replace('/home/vostrikov/', '')


def categorize(snippet):
    if NOT_READ_FIRST.search(snippet):
        return "not-read-first"
    if STRING_NOT_FOUND.search(snippet):
        return "string-not-found"
    if NOT_UNIQUE.search(snippet):
        return "not-unique"
    if DENY_RULE.search(snippet):
        return "deny-permission"
    return "other"


cat_by_proj = collections.defaultdict(collections.Counter)
cat_total = collections.Counter()
reread_by_proj = collections.Counter()
reread_total = 0
runs = 0

for f in files:
    try:
        d = json.load(open(f))
    except Exception:
        continue
    p = proj(f)
    runs += 1
    for tf in (d.get('tool_failures') or []):
        if tf.get('tool') not in ('Edit', 'Write', 'MultiEdit'):
            continue
        c = categorize(tf.get('snippet', ''))
        cat_by_proj[p][c] += 1
        cat_total[c] += 1
    rd = d.get('reads') or {}
    extra = sum(x.get('count', 0) - 1 for x in (rd.get('top_rereads') or []))
    reread_by_proj[p] += extra
    reread_total += extra

print(f"runs={runs}")
print()
print("=== Edit/Write tool_failures — категория × count (тотал) ===")
for cat, n in cat_total.most_common():
    print(f"  {cat:<20}{n}")
print(f"  {'TOTAL':<20}{sum(cat_total.values())}")
print()
print("=== по проектам (top-3 категории) ===")
for p, c in sorted(cat_by_proj.items(), key=lambda kv: -sum(kv[1].values())):
    print(f"  {p}: {dict(c.most_common())}")
print()
print(f"reread(extra, top_rereads-капнутая оценка) total={reread_total}")
for p, n in reread_by_proj.most_common():
    if n:
        print(f"  {p}: {n}")
