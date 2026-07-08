# Instructions for AI Agents

## Overview
This is a market-integration demo module that combines real community content:
- Skills from Anthropic (agentskills.io)
- Soul from SoulSpec (soulspec.org)
- This AGENTS.md follows the agents.md standard

## Repository Structure
- `skills/` -- Agent Skills bundles (SKILL.md format)
- `souls/` -- SoulSpec bundles (soul.json + SOUL.md)
- `manifest.yaml` -- Module manifest

## Testing
Run the demo script to verify all market content loads correctly:
```bash
cd python && uv run python ../examples/market-integration/demo.py
```
