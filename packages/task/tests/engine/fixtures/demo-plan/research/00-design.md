# Config validation design

## 1. Overview

Loader sketch; not needed by P1.2.

## 2. Validation

Collect every problem into one `ConfigError`:

```text
## not a heading, just fenced text
```

- required keys are listed in `REQUIRED_KEYS`
- types are checked after presence

### 2.1 Error format

One line per issue: `key: problem`.

## 3. Out of scope

Config file format stays as is.
