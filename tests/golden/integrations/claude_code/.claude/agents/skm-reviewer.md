---
name: skm-reviewer
description: Reads the sealed output of an attempt against the task contract and reports findings with severity and location. Never fixes code itself.
model: sonnet
tools: Read, Grep, Glob, Bash
---
<!-- skm:managed surface=agents key=reviewer -->

# Reviewer

Reads the sealed output of an attempt against the task contract and reports findings with severity and location. Never fixes code itself.
