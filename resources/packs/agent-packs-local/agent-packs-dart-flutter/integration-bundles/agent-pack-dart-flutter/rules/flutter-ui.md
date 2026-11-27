---
paths: ["lib/**/ui/**/*.dart", "lib/**/widgets/**/*.dart", "lib/**/presentation/**/*.dart"]
---

# Flutter UI

- Keep build methods free of side effects. Initiate asynchronous work through lifecycle methods or event handlers.
- Keep state near its owner and use focused widgets or selectors to limit rebuilds.
- Handle loading, empty, error, and success states. Preserve focus, semantic labels, and text scaling.
- Add widget tests for behavior and state transitions that users rely on.
