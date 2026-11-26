# Optional enforced consumer boundary

Use a permission preset only when the owner chooses this boundary for consumer work. Inspect
the installed Harness CLI help and effective settings. It must not accidentally forbid the
owning package repository during authorized development.

```json
{
  "permissions": {
    "deny": ["Write(vendor/**)", "Edit(vendor/**)"]
  }
}
```

A local `packages/` directory can contain owned development sources, not merely dependencies;
do not deny all package paths by name. Scope any path-repository restriction to the actual
consumer authority. An actual deny remains enforced: use an authorized owning-source route or
report the permission boundary. Do not remove or work around it just because a skill permits
a repair. A separate session is needed only for a real context/capability boundary or request.
