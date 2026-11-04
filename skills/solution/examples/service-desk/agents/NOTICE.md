# Fixtures da agent-review — agentes fictícios

Seis agentes do Copilot Studio de uma loja **fictícia** ("Bodega Azul"), no formato de um clone da extensão do
VS Code, para testar a agent-review. Nenhum dado real de cliente.

- Gerados pelo sub-agente Author do plugin **microsoft/skills-for-copilot-studio** (MIT, commit 9c42d3a), a partir dos
  modelos e das fixtures desse repositório (`templates/`, `evals/fixtures/`). Licença em
  `LICENSE-microsoft-skills-for-copilot-studio`.
- `gen_fixtures.py` regera o conjunto.
- `EXPECTED.md` é o gabarito: o que cada agente tem. Os testes do extrator devem bater com ele.

## Validação (schema-lookup validate do plugin)

- 69 de 75 arquivos passam sem falha.
- Os 6 `settings.mcs.yml` falham com "No 'kind' property found at root level" — **igual à fixture da própria
  Microsoft** (`evals/fixtures/basic-agent/settings.mcs.yml`). Lição para o extrator: identificar `settings` pelo
  nome do arquivo, não pelo `kind`.
- O validador completo (o da extensão do VS Code) exige conexão com um ambiente real e não foi rodado.

## Formatos inferidos (não vistos num clone real) — conferir com agentes de um ambiente de teste próprio, fora do cliente

Ver a seção de incertezas do `EXPECTED.md`. As principais:
1. Orquestrador → especialista conectado: `actions/*.mcs.yml` com `TaskDialog` + `InvokeConnectedAgentTaskAction`.
2. Lado do especialista: tópico `OnRedirect` + `isExternalInitializationAllowed` / `isAgentConnectable`.
3. Variáveis globais: forma "plana" do modelo do plugin, não a aninhada do esquema.
4. `connectionreferences.mcs.yml`: montado pelo esquema, sem exemplo real.
5. Sem a pasta oculta `.mcs/` (um clone real tem `.mcs/conn.json` com IDs do ambiente).
