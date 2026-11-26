"""Resolve the executor identity used for a work claim."""


def claim_actor(self) -> str:
    """Who runs the work, as claimed: the executor the run was started with (the ``executor`` stage of ``--options``:
    its provider, its model or the model of its class, and its effort), else the default executor (provider and model,
    no effort). The source checks the route of the work against this actor at the claim; an executor the options name
    but the claim does not carry is refused as ``ROUTE_MISMATCH`` / ``ROUTE_UNDERSHOOT`` before any work began, while
    the dry run, which builds the route from the same options, shows it green. Registration still checks the route
    against the executor that really ran."""
    stage = self._invocation_executor()
    provider = stage.get("provider") or self.conductor.get("provider") or "claude-code"
    entry = self._entry("executor", provider)
    model = stage.get("model")
    if not model:
        model_class = stage.get("model_class") or entry["model_class"]
        model = self._catalog_get().resolve_model(provider, model_class) if entry["model_set"] == "supported" \
            else "default"
    return "/".join(part for part in (provider, model, stage.get("effort")) if part)


def claim_actor_source(self) -> tuple:
    """``(source, fields, model_class)`` of the claim actor for the work source, as the stage merge of execution sees
    the ``executor`` stage of ``--options``: ``fields`` are the actor fields it names (provider, model, effort; a
    provider alone keeps the plan's model, as the merge does), ``model_class`` a class it names without a model (the
    source resolves its model on the provider of the merged actor). ``("default", None, None)`` when it names none of
    them: the source may use the executor of its own plan."""
    stage = self._invocation_executor()
    fields = [name for name in ("provider", "model", "effort") if stage.get(name)]
    model_class = stage.get("model_class") if not stage.get("model") else None
    return ("options", fields or None, model_class) if fields or model_class else ("default", None, None)
