# Security Policy

## Report a vulnerability

Found a security problem - write to **dv.vostrikov@gmail.com** (topic: `maind security`).
Please do not open public issue until disclosure is agreed upon.

## Trust Model

- **The memory daemon listens only localhost** (`127.0.0.1:4111/4112` default). Not
  expose the ports to the outside without a separate reverse-proxy with authentication - the daemon does not have
  own authorization.
- **maind does not kill someone else's process.** If the daemon responds but is not started via maind (no
  pidfile in `data/`), `maind memory stop` doesn't touch him.
- **Isolation between projects - logical** (by `namespace`/scope), within one
  trusted daemon. This is not a security boundary between mutually untrusted parties.

## Secrets

- Keys and tokens - only in `.env` (gitignored). Never commit `.env`, real
  `config.json` or contents `data/`.
- `ANTHROPIC_API_KEY` (optional, for memory compression) is stored in `.env`, is not in the config.

## Dependencies

- Python-runtime — **only stdlib** (minimum attack surface). Third Party Packages
  (`@agentmemory/agentmemory`, optional `networkx`/`graphify`) are set explicitly.
