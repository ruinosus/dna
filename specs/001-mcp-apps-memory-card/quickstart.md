# Quickstart — validar o card de memória MCP Apps

**Phase 1 do `/speckit-plan`** — guia de validação ponta a ponta.
Referências: [contrato da superfície MCP](contracts/mcp-surface.md),
[data model](data-model.md).

## Pré-requisitos

- Python 3.12 + venv com `-e packages/sdk-py -e packages/cli` (extras dev).
- Node (para o smoke com o `basic-host` do `ext-apps`).
- `fastmcp>=3.2` resolvido no ambiente (hoje resolve 3.4.4).

## 1. Test-gate do lado SDK

```bash
python -m pytest packages/sdk-py/tests/test_emit_mcp_ui.py packages/cli/tests/test_mcp_apps.py -v
```

Esperado — todos verdes, cobrindo as mutações declaradas no design:

- golden byte-stable do template (conteúdo novo, disciplina mantida);
- declaração de `list_memories`/`recall` carrega o `resourceUri`
  (pointer removido → morre);
- `resources/read` de `ui://dna/memory-list` responde com
  `text/html;profile=mcp-app` (registro removido → morre);
- HTML do template sem dados de memória (dados assados → morre) e sem URL
  externa (CDN → morre);
- **grep-guard §3**: `TODO` / `deferred` / `follow-up` / `coming soon` na
  superfície entregue quebra o teste (TODO plantado → morre).

## 2. Degradação byte-idêntica

Num cliente sem a extensão, comparar o `content` textual de
`list_memories`/`recall` antes/depois da entrega: byte-idêntico.

## 3. Smoke de render real (sem host comercial)

Servir o MCP local e abrir com o `basic-host` do `ext-apps`; invocar
`list_memories` → o card renderiza; com zero memórias → empty state
"nenhuma memória".

## 4. Console do portal (repo dna-cloud, após release+pin)

Teste node: o `@ag-ui/mcp-apps-middleware` está no pipeline do runtime do
copiloto e o card do fixture renderiza. Validação visual no `/console` é
gate de deploy. O painel lateral "Memória" permanece inalterado.

## 5. Aceitação final (gate de `story done` do lado SDK)

Custom connector no Claude.ai (fundador): card renderizando com dados reais,
junto do test-gate. Nenhuma ação disponível no card (só leitura).
