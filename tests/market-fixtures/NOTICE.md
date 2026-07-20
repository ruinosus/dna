# Market-fixture provenance (F3 conformance)

These fixtures are **real artifacts downloaded from the market** — the
conformance suite (`packages/sdk-py/tests/test_market_conformance.py`)
proves they load, type,
compose and write back **without any adaptation** (spec §2.1: the standard
owner's native bundle, byte-faithful).

| File | Real or derived | Origin | Fetched |
|---|---|---|---|
| `.dna/market-conformance/AGENTS.md` | **real** (verbatim) | https://raw.githubusercontent.com/openai/codex/main/AGENTS.md (openai/codex, agents.md standard) | 2026-07-08 |
| `.dna/market-conformance/souls/starter/SOUL.md` | **real** (verbatim) | https://raw.githubusercontent.com/clawsouls/soulclaw/develop/docs/reference/templates/SOUL.md (soulspec.org standard owner's published workspace template) | 2026-07-08 |
| `.dna/market-conformance/souls/starter/IDENTITY.md` | **real** (verbatim) | https://raw.githubusercontent.com/clawsouls/soulclaw/develop/docs/reference/templates/IDENTITY.md | 2026-07-08 |
| `.dna/market-conformance/souls/starter/HEARTBEAT.md` | **real** (verbatim) | https://raw.githubusercontent.com/clawsouls/soulclaw/develop/docs/reference/templates/HEARTBEAT.md | 2026-07-08 |
| `.dna/market-conformance/Genome.yaml` | ours (scaffold) | scope-root identity doc — not market content | — |
| `.dna/market-conformance/agents/conductor.yaml` | ours (scaffold) | composition probe — not market content | — |

The 31 Skill bundles under `scopes/market-integration/` (including `xlsx`,
`docx`, `pdf`, `pptx`) are likewise **real** Anthropic marketplace /
community skills, copied byte-faithful; the `brad` soul there is a real
clawsouls community persona (`soul.json` → `"author": "clawsouls"`).

Licenses: openai/codex is Apache-2.0; the soulspec templates are published
under the soulclaw repo's license (MIT); each skill bundle carries its own
`LICENSE.txt` where the marketplace ships one. Fixtures are used here for
interoperability testing only.
