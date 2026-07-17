# 003 - Websearch Integration Into Lincoln Prompt

## Date: 2026-07-17

## Decision
Integrate websearch directly into Lincoln's > prompt
so no /run prefix is needed.

## Goal
> websearch "query" 5
Works natively inside Lincoln without leaving the prompt.

## Approach
Aider message prefix handler wrapping web_search.py
Results inject automatically into Qwen context.

## Reasoning
One terminal. One prompt. No manual steps. Fully agentic.