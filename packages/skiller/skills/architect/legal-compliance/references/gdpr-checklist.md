# Standard checklist GDPR (minimum baseline)

Skill reference `legal-compliance`.


### 1. Legal basis for processing
For **each data category** select one of 6 bases:
- Consent (opt-in, withdrawable)
- Contract (is necessary to fulfill the contract with the user)
- Legal obligation
- Vital interests
- Public task
- Legitimate interests (requires balance test)

### 2. Data inventory (Article 30 records)
Table for each category:

| Data | Purpose | Legal basis | Retention | Storage | Recipients | Cross-border? |
|:---|:---|:---|:---|:---|:---|:---|

### 3. User rights implementation
- **Access** (Article 15) — export user data in machine-readable format
- **Correction** (Article 16) — UI or support flow
- **Removal** (Article 17, «right to be forgotten») — cascade across all repositories, backups, logs, analytics
- **Portability** (Article 20) — JSON/CSV export
- **Objection** (Article 21) — opt-out from marketing/profiling

Each right → specific endpoint / UI flow / SLA response (1 month to GDPR).

### 4. Consent management
- Granular opt-in (not alone «accept everything»)
- Cookie banner matches ePrivacy (no «press X = consent»)
- Record consent (when, version policy, IP) with retention

### 5. Privacy Policy + ToS
Created as draft. The lawyer brings it to the end.

### 6. DPA with processors
For everyone external service (AWS, Stripe, OpenAI, analytics):
- Signed DPA
- Storage region
- SCC if cross-border (EU → US)

### 7. Breach response plan
- Internal flow: detection → assessment → containment → notification
- SLA: 72 hours for notification DPA when high-risk breach
- Template notifications ready in advance

---
