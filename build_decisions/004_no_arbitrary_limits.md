# 004 - No Arbitrary Limits On Content

## Date: 2026-07-17

## Decision
Remove all arbitrary content limits from Lincoln's tools.

## Changes
- web_search.py fetch: removed 3000 character cutoff, full page content flows
- web_search.py timeout: increased from 10s to 30s for slow academic sites

## Reasoning
Lincoln is an AI agent with 256K token context window.
Arbitrary limits on content defeat the purpose of an agentic system.
Qwen should see full content and reason over it completely.
Full content in, better reasoning out.

## Principle
Never set arbitrary limits without explicit justified reason.
Document any limits that do exist and why.