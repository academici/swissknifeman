# Optional source layouts

Discover ownership before choosing a layout. The skill's SSOT contract applies to each semantic
identity, not to a universal filesystem location.

| Existing project model | Authoritative source | Regeneration |
|---|---|---|
| Swissknifeman registry | Skiller package's `skills/` | Worktree-local Skiller registry/publisher |
| Project-authored `.ai` model | `.ai/skills/`, `.ai/guidelines/` | Its declared sync/compiler |
| Laravel Boost integration | Installed-version supported inputs/config | Verified project Boost pipeline |
| Native plugins | Selected package source/manifest | Package publisher and provider update |
| Handwritten agent docs | Owned file or handwritten region | No generator unless explicitly adopted |

Multiple generators may coexist when they own separate outputs or compose via explicit source
extension points. A Boost dependency does not transfer ownership of unrelated project docs.
Check commands and supported fields against the installed version; examples are not a schema.

Track source and generated outputs according to repository policy. Generated agent manifests
may intentionally be committed. Never infer mass `.gitignore`/`git rm --cached` changes from
this example. Preserve distinct local customization, ownership locks and user settings.

After edits run the owning generator/check and inspect effective provider discovery. Deleting a
filesystem duplicate needs proven managed ownership and retained equivalent behavior. Record
source/installed/loaded-session state separately; a cached session may still use earlier rules.
