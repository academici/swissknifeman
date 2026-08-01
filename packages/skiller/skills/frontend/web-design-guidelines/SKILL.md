---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

Review files for compliance with Web Interface Guidelines.

## How It Works

1. Read the rules from the vendored payload: [`references/web-interface-guidelines.md`](references/web-interface-guidelines.md)
2. Read the specified files (or prompt user for files/pattern)
3. Check against all rules in the payload
4. Output findings in the terse `file:line` format

## Guidelines Source

Rules are vendored locally — pinned `vercel-labs/web-interface-guidelines` commit
`4e799d45c17aec1498c269287a83b9dba22b966b` (provenance and re-pinning procedure in
`upstream.json`). No network fetch: read
[`references/web-interface-guidelines.md`](references/web-interface-guidelines.md) directly.

## Usage

When a user provides a file or pattern argument:
1. Read `references/web-interface-guidelines.md`
2. Read the specified files
3. Apply all rules from the payload
4. Output findings using the format specified in the payload

If no files specified, ask the user which files to review.
