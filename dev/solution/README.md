# solution

A **solution** is one process seen by every skill that has something to say about it — the way of working
(way-of-working), the «what if» simulation (process-simulation), the customer's journey (service-blueprint), the incident
drill (incident-drill), the Copilot Studio agents (agent-review), the lesson that explains it (visual-explainer) — kept in one
short file beside the pieces:

```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: Solution
metadata:
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
npx @ruinosus/dna solution --list
npx @ruinosus/dna solution --new service-desk my-desk
npx @ruinosus/dna solution my-desk/service-desk.solution.yaml --check
npx @ruinosus/dna solution my-desk/service-desk.solution.yaml
```

The skill is in [`skills/solution`](../../skills/solution/SKILL.md); its format in
[`references/format.md`](../../skills/solution/references/format.md). Tools: `npm run check|zip|site -w
dev/solution/tools`.
