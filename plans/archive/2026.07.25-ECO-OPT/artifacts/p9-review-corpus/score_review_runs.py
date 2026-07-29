#!/usr/bin/env python3
"""score_review_runs.py — детерминированный скорер эталон-корпуса ревью (P9.3,
2026.07.25-ECO-OPT). stdlib-only, без сети и без вызова модели. Правило матчинга —
`matching-rules.md` (тот же файл · пересечение строк ±10 · совпадение type · one-to-one
жадное сопоставление; неоднозначность печатает пару и падает — арбитраж человеческий,
LLM-judge запрещён).

Вход: --runs runs-baseline.csv (сырьё прогонов) + --key answer-key.json (ключ,
must_find/is_trap) + --rules matching-rules.md (не парсится — путь только для
трассируемости вызова в Validation). Выход: JSON с J/U1/R/R1 и тремя корзинами
(matched TP / judged FP / plausible but unlabeled).

--self-test: синтетика с РУКАМИ посчитанным Jaccard (см. `_self_test`) — измеритель,
который никто не проверил, измеряет себя.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

SLACK_LINES = 10


def eligible(a_from, a_to, b_from, b_to, slack=SLACK_LINES):
    """Пересечение диапазонов строк ±slack (matching-rules.md, условие 3)."""
    return a_from <= b_to + slack and a_to >= b_from - slack


def overlap_score(a_from, a_to, b_from, b_to):
    """Ширина пересечения (>0 — реальное пересечение; <=0 — разрыв в пределах slack,
    используется только для ранжирования кандидатов, не для допуска — допуск даёт eligible())."""
    return min(a_to, b_to) - max(a_from, b_from)


def load_key(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["findings"]


def load_runs(path):
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append({
                "case_id": row["case_id"],
                "run_idx": row["run_idx"],
                "finding_id_local": row["finding_id_local"],
                "file": row["file"],
                "line_from": int(row["line_from"]),
                "line_to": int(row["line_to"]),
                "type": row["type"],
                "severity": row.get("severity", ""),
                "statement": row.get("statement", ""),
            })
        return rows


def match_case_run(key_findings, run_findings, rejected_pairs=frozenset()):
    """One-to-one жадное сопоставление находок одного (case_id, run_idx) против ключа
    ЭТОГО кейса (must_find + is_trap — обе группы участвуют как цели матчинга).
    `rejected_pairs` — арбитраж человека по неоднозначностям (см. arbitration.json):
    множество (kf_finding_id, rf_finding_id_local) пар, ИСКЛЮЧАЕМЫХ из кандидатов
    (арбитр решил — это НЕ та же находка, несмотря на формальное совпадение
    файл/тип/диапазон). Возвращает (matches, unmatched_run_findings) или бросает
    AmbiguousMatch, если после исключений неоднозначность осталась НЕразрешённой."""
    candidates = []
    for kf in key_findings:
        kloc = kf["location"]
        for rf in run_findings:
            if kloc["file"] != rf["file"]:
                continue
            if kf["type"] != rf["type"]:
                continue
            if not eligible(rf["line_from"], rf["line_to"], kloc["line_from"], kloc["line_to"]):
                continue
            if (kf["finding_id"], rf["finding_id_local"]) in rejected_pairs:
                continue
            score = overlap_score(rf["line_from"], rf["line_to"], kloc["line_from"], kloc["line_to"])
            candidates.append((score, kf["finding_id"], id(rf), kf, rf))

    candidates.sort(key=lambda c: -c[0])

    used_kf = set()
    used_rf = set()
    matches = []
    for i, (score, kf_id, rf_id, kf, rf) in enumerate(candidates):
        if kf_id in used_kf or rf_id in used_rf:
            continue
        ties = [
            c for c in candidates
            if c[0] == score and (c[1], c[2]) != (kf_id, rf_id)
            and c[1] not in used_kf and c[2] not in used_rf
            and (c[1] == kf_id or c[2] == rf_id)
        ]
        if ties:
            other = ties[0]
            raise AmbiguousMatch(
                f"неоднозначный матч (score={score}): "
                f"({kf_id!r}, run-finding file={rf['file']}:{rf['line_from']}-{rf['line_to']}) "
                f"vs ({other[3]['finding_id']!r}, run-finding file={other[4]['file']}:"
                f"{other[4]['line_from']}-{other[4]['line_to']}) — арбитраж человека, не эвристика."
            )
        used_kf.add(kf_id)
        used_rf.add(rf_id)
        matches.append((kf, rf))

    unmatched_run = [rf for rf in run_findings if id(rf) not in used_rf]
    return matches, unmatched_run


class AmbiguousMatch(RuntimeError):
    pass


def score(key_findings, runs, rejected_pairs=frozenset()):
    """Считает метрики по ВСЕМУ корпусу (все case_id, все run_idx). runs — плоский список
    записей load_runs(); key_findings — плоский список answer-key.json['findings'].
    `rejected_pairs` — арбитраж человека, см. match_case_run()."""
    by_case_key = {}
    for kf in key_findings:
        by_case_key.setdefault(kf["case_id"], []).append(kf)

    by_case_run = {}
    for rf in runs:
        by_case_run.setdefault(rf["case_id"], {}).setdefault(rf["run_idx"], []).append(rf)

    matched_tp = []       # (case_id, run_idx, finding_id ключа)
    judged_fp = []        # (case_id, run_idx, finding_id ключа-ловушки)
    plausible_unlabeled = []  # (case_id, run_idx, file, line_from, line_to)

    per_run_recall = []   # одна запись на (case_id, run_idx)
    found_at_least_once = {}  # (case_id, finding_id must_find) -> set(run_idx)
    jaccard_by_case = {}  # case_id -> {run_idx: set(finding_id)}

    for case_id, key_list in by_case_key.items():
        must_find_ids = {kf["finding_id"] for kf in key_list if kf.get("must_find")}
        runs_for_case = by_case_run.get(case_id, {})
        case_jaccard_sets = {}
        for run_idx, run_findings in runs_for_case.items():
            matches, unmatched = match_case_run(key_list, run_findings, rejected_pairs)
            case_tp_ids = set()
            for kf, rf in matches:
                if kf.get("must_find"):
                    matched_tp.append((case_id, run_idx, kf["finding_id"]))
                    case_tp_ids.add(kf["finding_id"])
                    found_at_least_once.setdefault((case_id, kf["finding_id"]), set()).add(run_idx)
                elif kf.get("is_trap"):
                    judged_fp.append((case_id, run_idx, kf["finding_id"]))
            for rf in unmatched:
                plausible_unlabeled.append((case_id, run_idx, rf["file"], rf["line_from"], rf["line_to"]))
            case_jaccard_sets[run_idx] = case_tp_ids
            if must_find_ids:
                per_run_recall.append(len(case_tp_ids) / len(must_find_ids))
        jaccard_by_case[case_id] = case_jaccard_sets

    # R: pass@3 по ключу — доля must_find находок, пойманных хотя бы одним прогоном СВОЕГО кейса.
    total_must_find = sum(1 for kf in key_findings if kf.get("must_find"))
    found_ids = {k for k, runs_seen in found_at_least_once.items() if runs_seen}
    R = (len(found_ids) / total_must_find) if total_must_find else None

    # R1: медиана recall одного прогона.
    R1 = statistics.median(per_run_recall) if per_run_recall else None

    # J: медиана попарного Jaccard между прогонами одного кейса.
    jaccards = []
    for case_id, run_map in jaccard_by_case.items():
        run_idxs = sorted(run_map)
        for i in range(len(run_idxs)):
            for j in range(i + 1, len(run_idxs)):
                a, b = run_map[run_idxs[i]], run_map[run_idxs[j]]
                union = a | b
                inter = a & b
                jaccards.append(len(inter) / len(union) if union else 1.0)
    J = statistics.median(jaccards) if jaccards else None

    # U1: доля найденных (хотя бы раз) must_find находок, найденных РОВНО одним прогоном.
    counts = [len(runs_seen) for runs_seen in found_at_least_once.values() if runs_seen]
    U1 = (sum(1 for c in counts if c == 1) / len(counts)) if counts else None

    return {
        "J": J,
        "U1": U1,
        "R": R,
        "R1": R1,
        "matched_tp": matched_tp,
        "judged_fp": judged_fp,
        "plausible_but_unlabeled": plausible_unlabeled,
        "total_must_find": total_must_find,
        "pairwise_jaccard_count": len(jaccards),
        "per_run_recall_count": len(per_run_recall),
    }


def _self_test():
    """Синтетика: 4 must_find находки одного кейса, 2 прогона. Jaccard/recall/U1/R
    посчитаны руками ниже и сверены с выводом score()."""
    key = [
        {"finding_id": "K1", "case_id": "SELFTEST", "type": "product", "must_find": True,
         "location": {"file": "f.py", "line_from": 10, "line_to": 10}},
        {"finding_id": "K2", "case_id": "SELFTEST", "type": "product", "must_find": True,
         "location": {"file": "f.py", "line_from": 30, "line_to": 30}},
        {"finding_id": "K3", "case_id": "SELFTEST", "type": "product", "must_find": True,
         "location": {"file": "f.py", "line_from": 50, "line_to": 50}},
        {"finding_id": "K4", "case_id": "SELFTEST", "type": "product", "must_find": True,
         "location": {"file": "f.py", "line_from": 70, "line_to": 70}},
    ]
    runs = [
        {"case_id": "SELFTEST", "run_idx": "A", "finding_id_local": "a1", "file": "f.py",
         "line_from": 10, "line_to": 10, "type": "product", "severity": "Major", "statement": "x"},
        {"case_id": "SELFTEST", "run_idx": "A", "finding_id_local": "a2", "file": "f.py",
         "line_from": 30, "line_to": 30, "type": "product", "severity": "Major", "statement": "x"},
        {"case_id": "SELFTEST", "run_idx": "A", "finding_id_local": "a3", "file": "f.py",
         "line_from": 50, "line_to": 50, "type": "product", "severity": "Major", "statement": "x"},
        {"case_id": "SELFTEST", "run_idx": "B", "finding_id_local": "b1", "file": "f.py",
         "line_from": 10, "line_to": 10, "type": "product", "severity": "Major", "statement": "x"},
        {"case_id": "SELFTEST", "run_idx": "B", "finding_id_local": "b2", "file": "f.py",
         "line_from": 30, "line_to": 30, "type": "product", "severity": "Major", "statement": "x"},
        {"case_id": "SELFTEST", "run_idx": "B", "finding_id_local": "b3", "file": "f.py",
         "line_from": 70, "line_to": 70, "type": "product", "severity": "Major", "statement": "x"},
    ]
    # Руками: A -> {K1,K2,K3}, B -> {K1,K2,K4}. Jaccard(A,B) = |{K1,K2}| / |{K1,K2,K3,K4}| = 2/4 = 0.5.
    # recall(A) = 3/4 = 0.75, recall(B) = 3/4 = 0.75 -> медиана = 0.75.
    # R = найдено хотя бы раз: {K1,K2,K3,K4} = 4/4 = 1.0.
    # U1: K1 в 2 прогонах, K2 в 2, K3 в 1, K4 в 1 -> найдено-хотя-бы-раз=4, ровно-1=2 -> 0.5.
    result = score(key, runs)
    checks = [
        (result["J"], 0.5, "J"),
        (result["R1"], 0.75, "R1"),
        (result["R"], 1.0, "R"),
        (result["U1"], 0.5, "U1"),
    ]
    ok = True
    for actual, expected, name in checks:
        status = "OK" if actual == expected else "FAIL"
        if actual != expected:
            ok = False
        print(f"self-test {name}: expected={expected} actual={actual} [{status}]")

    # Ambiguity: две находки ключа с ОДИНАКОВЫМ пересечением одной находки прогона.
    ambiguous_key = [
        {"finding_id": "AMB1", "case_id": "SELFTEST2", "type": "product", "must_find": True,
         "location": {"file": "g.py", "line_from": 10, "line_to": 20}},
        {"finding_id": "AMB2", "case_id": "SELFTEST2", "type": "product", "must_find": True,
         "location": {"file": "g.py", "line_from": 12, "line_to": 22}},
    ]
    ambiguous_runs = [
        {"case_id": "SELFTEST2", "run_idx": "A", "finding_id_local": "a1", "file": "g.py",
         "line_from": 15, "line_to": 17, "type": "product", "severity": "Major", "statement": "x"},
    ]
    try:
        score(ambiguous_key, ambiguous_runs)
        print("self-test ambiguity: expected AmbiguousMatch, got none [FAIL]")
        ok = False
    except AmbiguousMatch:
        print("self-test ambiguity: raised AmbiguousMatch as expected [OK]")

    return ok


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--runs")
    ap.add_argument("--key")
    ap.add_argument("--rules", help="путь к matching-rules.md (не парсится, только трассируемость вызова)")
    ap.add_argument("--arbitration", help="путь к arbitration.json — человеческий арбитраж неоднозначных пар")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv[1:])

    if args.self_test:
        ok = _self_test()
        return 0 if ok else 1

    if not args.runs or not args.key:
        ap.error("--runs и --key обязательны (или --self-test)")

    key_findings = load_key(args.key)
    runs = load_runs(args.runs)
    rejected_pairs = frozenset()
    if args.arbitration:
        arb = json.loads(Path(args.arbitration).read_text(encoding="utf-8"))
        rejected_pairs = frozenset(
            (d["key_finding_id"], d["run_finding_id_local"])
            for d in arb["decisions"] if d["verdict"] == "reject"
        )
    try:
        result = score(key_findings, runs, rejected_pairs)
    except AmbiguousMatch as exc:
        print(f"AMBIGUOUS: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"J={result['J']} U1={result['U1']} R={result['R']} R1={result['R1']}")
        print(f"matched_tp={len(result['matched_tp'])} judged_fp={len(result['judged_fp'])} "
              f"plausible_but_unlabeled={len(result['plausible_but_unlabeled'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
