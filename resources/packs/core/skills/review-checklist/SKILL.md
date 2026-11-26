---
name: review-checklist
description: "Apply a modular review checklist to a sealed change: contracts, tests, failure paths, and scope, without modifying files."
---
# Review Checklist

Use this checklist with the loaded review method. It lists what to cover. It does not replace the method or the result contract.

## Checklist
1. Map each changed behavior to its governing contract, acceptance criteria, and recorded check evidence.
2. Follow affected call sites, state transitions, invariants, and error paths to the depth the work policy requires.
3. Confirm tests assert the changed paths and the error branches the diff introduces.
4. Note missing or conflicting check evidence as a concrete risk. Do not rerun broad suites.
5. Keep findings inside the sealed change. Do not report style preferences or speculative redesigns as blockers.
6. Do not edit, create, or delete repository files.
