def validate_exception_target(plan_dir, exception, *, check_duplicate=True):
    """Проверяет provenance, owner gate и точное множество waived schema-полей.

    Sidecar физически отделён от event-журнала, поэтому exception не может ссылаться
    на другое exception и correction-цикл конструктивно невозможен.
    """
    validate_exception(exception)
    plan_dir = Path(plan_dir)
    canonical_plan_id = plan_dir.name
    if exception["plan_id"] != canonical_plan_id:
        raise JournalValidationError(
            f"exception: plan_id «{exception['plan_id']}» ≠ canonical plan directory "
            f"«{canonical_plan_id}»")
    journal_path = plan_dir / FILENAME
    try:
        lines = journal_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise JournalValidationError(f"target journal не читается: {exc}") from exc

    target_line = exception["target_line"]
    if target_line > len(lines) or not lines[target_line - 1].strip():
        raise JournalValidationError("target_line: нет такой непустой строки journal")
    raw_line = lines[target_line - 1]
    if line_sha256(raw_line) != exception["target_sha256"]:
        raise JournalValidationError("target_sha256: не совпадает с raw journal line")
    try:
        target = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        raise JournalValidationError(
            "target: malformed JSON не допускает schema exception") from exc
    target_plan_id = target.get("plan_id") if isinstance(target, dict) else None
    if target_plan_id != canonical_plan_id:
        raise JournalValidationError(
            f"target event: plan_id «{target_plan_id}» ≠ canonical plan directory "
            f"«{canonical_plan_id}»")

    target_errors = entry_validation_errors(target)
    target_fields = {field for field, _ in target_errors}
    if not target_errors:
        raise JournalValidationError("target: строка уже проходит event-схему")
    if target_fields != set(exception["invalid_fields"]):
        raise JournalValidationError(
            f"invalid_fields: ожидалось точное множество {sorted(target_fields)}")

    try:
        plan_text = (plan_dir / "plan.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise JournalValidationError(f"plan.md не читается: {exc}") from exc
    decision = re.escape(exception["owner_decision"])
    if not re.search(rf"^\|\s*{decision}\s*\|", plan_text, re.MULTILINE):
        raise JournalValidationError("owner_decision: D# отсутствует в plan.md")

    if check_duplicate:
        exceptions_path = plan_dir / EXCEPTIONS_FILENAME
