# opening-night

A **solution** is one process seen by every skill that has something to say about it — the way of working
(gates-and-handoffs), the «what if» simulation (box-office), the customer's journey (service-blueprint), the incident
drill (dress-rehearsal), the Copilot Studio agents (cast-list), the lesson that explains it (chalk-talk) — kept in one
short file beside the pieces:

```yaml
format: opening-night/v1
name: Central de atendimento
about: Do chamado do cliente ao encerramento.
lang: pt
way: service-desk.way.yaml
sim: service-desk.sim
blueprint: service-desk.blueprint.yaml
drill: service-desk.drill.yaml
agents: agents
profile: profile.cast.yaml
```

`--check` checks each piece with its own skill and says which lens fell behind the way; the page is one offline file,
a summary and a tab per piece, each drawn by its skill. **Solution accelerators** to start from: an employee
self-service assistant with Workday (after Microsoft's public sample), a customer service desk with its six agents, the
delivery of an assistant.

```
npx house-lights opening-night --list
npx house-lights opening-night --new service-desk my-desk
npx house-lights opening-night my-desk/service-desk.solution.yaml --check
npx house-lights opening-night my-desk/service-desk.solution.yaml
```

The skill is in [`skills/opening-night`](../../skills/opening-night/SKILL.md); its format in
[`references/format.md`](../../skills/opening-night/references/format.md). Tools: `npm run check|zip|site -w
dev/opening-night/tools`.
