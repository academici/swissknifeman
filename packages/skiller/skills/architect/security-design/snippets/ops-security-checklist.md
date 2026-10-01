# Operational Security Checklist (according to guidelines Spatie)

<!-- Source: anonymized production Laravel project (adaptation https://spatie.be/guidelines/security) -->

Apply when configuring the application, database and servers, as well as when security-code and infrastructure review. Complements the architectural steps of the main skill (OWASP, STRIDE) operating rules «here and now».

## Appendix

- [ ] All HTTP-traffic - only by SSL/TLS (including redirect from http and HSTS)
- [ ] CSRF-tokens on all forms
- [ ] Significant Actions (mutations) — only via POST/PUT/DELETE, never GET
- [ ] Authorization autotests: check that closed functionality is visible only to authorized roles

## Database

- [ ] All stored passwords are hashes only (bcrypt/argon2)
- [ ] API-keys in the database are encrypted
- [ ] Separate DB-user for each database with the minimum required read rights/entries
- [ ] Access to the database - only with whitelist-hosts (web server and development machines)

## Server

- [ ] NGINX, PHP, OS and related software are updated regularly
- [ ] SSH — by keys only; password authentication disabled
- [ ] `unattended-upgrades` installed and enabled (automatic security-updates)
- [ ] Firewall skips only what is necessary (typically ports 22 and 443)
- [ ] Server management - via IaC (for example, Ansible): fast patching and revoking access

## Credits

- [ ] All passwords are in the password manager
- [ ] Each password is unique, no reuse
- [ ] 2FA enabled wherever available
- [ ] Private keys are password protected

## Backups and general

- [ ] Backups are configured and **are periodically checked by recovery**
- [ ] Full disk encryption on production machines
- [ ] No sensitive code/data in public services (Pastebin etc.)
- [ ] Browser extensions - only from official stores, to a minimum
