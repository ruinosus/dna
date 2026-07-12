---
apiVersion: github.com/ruinosus/dna/sdlc/v1
kind: Research
metadata:
  name: rsh-portfolio-enterprise-auth
spec:
  title: Enterprise auth do DNA Cloud — SSO (SAML+OIDC) + SCIM pra multinacionais
  status: published
  objective: 'Desenhar a camada de autenticacao/provisionamento enterprise que multinacionais exigem em
    procurement pro DNA Cloud (Organization multi-tenant). Ja temos OIDC/Entra. Suporta o adr-portfolio-project-model
    (fork #3 SSO/SCIM).'
  methodology: web-search-curated
  executive_summary: |
    Para o DNA Cloud vender pra multinacional, a evidencia aponta uma arquitetura clara:
    suportar SAML 2.0 E OIDC (SAML = table-stakes pro enterprise/governo; OIDC = default
    moderno, ja temos via Entra) — SaaS enterprise acaba shipando os dois pra evitar
    friccao de procurement. E implementar SCIM 2.0 (RFC 7643 schema + RFC 7644 protocolo)
    como Service-Provider expondo /Users e /Groups, pro IdP do cliente (Okta/Entra/Google)
    empurrar provisionamento automatico e — o mais importante — DEPROVISIONING automatico
    (active=false revoga acesso no instante que o funcionario sai; SSO sozinho nao faz isso,
    so aplica mudanca no proximo re-login). Deprovisioning e o item que a revisao de
    seguranca enterprise testa mais forte. Mapeamento grupo-do-IdP -> papel do produto
    (ex: 'Engineering-Admins' -> Admin) via SCIM /Groups (real-time), casando com a escada
    Owner/Admin/Member/Guest. SP-initiated SSO como default seguro (mas suportar IdP-initiated
    tambem). Movimento no1: SP-initiated SAML SSO com enforced-SSO, depois SCIM deprovisioning.
    ABERTO (a pesquisa nao confirmou): gating por tier (sso.tax), build-vs-buy (WorkOS/Auth0),
    e compliance (SOC 2) — tratar como follow-up.
  findings:
  - id: f-saml-and-oidc
    title: Suportar SAML 2.0 E OIDC — SAML e table-stakes pro enterprise/governo; OIDC e o default moderno
      (ja temos via Entra). SaaS enterprise shipa os dois pra evitar friccao
    evidence_rating: evidence-based
  - id: f-scim-deprovision
    title: 'SCIM 2.0 (/Users + /Groups) e o que da provisionamento automatico + DEPROVISIONING (active=false)
      — o valor de seguranca #1 que SSO sozinho nao faz; o que o security review testa'
    evidence_rating: evidence-based
  - id: f-groups-to-roles
    title: Grupo do IdP -> papel do produto (ex Engineering-Admins -> Admin) via SCIM /Groups push, casando
      com a escada Owner/Admin/Member/Guest
    evidence_rating: evidence-based
  - id: f-sp-initiated
    title: SP-initiated SSO como default seguro (replay/CSRF protection via InResponseTo); suportar IdP-initiated
      tambem (tiles Okta/Entra), mas SP-initiated e o seguro
    evidence_rating: evidence-based
  - id: f-open-forks
    title: 'NAO confirmado pela pesquisa: gating por tier (sso.tax), build-vs-buy (WorkOS/Auth0/Stytch),
      compliance (SOC 2 Type II) — follow-up necessario'
    evidence_rating: opinion-practice
  recommendations:
  - id: rec-both-protocols
    priority: high
    summary: Adotar SAML 2.0 + OIDC. Ja temos OIDC/Entra → o caminho minimo e adicionar federacao SAML
      (SP-initiated default + enforced-SSO) sobre o que existe.
  - id: rec-scim-server
    priority: high
    summary: Implementar um servidor SCIM 2.0 (/Users + /Groups + endpoints de discovery), priorizando
      DEPROVISIONING (active=false) e o mapeamento grupo->papel. Movimento no1 de enterprise-ready.
  - id: rec-enterprise-tier
    priority: medium
    summary: 'Provisao: gatear SSO/SCIM no tier Enterprise (padrao de mercado), mas VALIDAR o packaging
      no follow-up (debate sso.tax) — nao assumir sem evidencia.'
  - id: rec-build-vs-buy-followup
    priority: medium
    summary: Avaliar build-vs-buy (WorkOS/Auth0 vs estender o OIDC/Entra que ja temos) + compliance minima
      (SOC 2 Type II, audit logs, session policy) num follow-up focado antes de commitar.
  created_at: '2026-07-12T22:36:53+00:00'
  updated_at: '2026-07-12T22:36:53+00:00'
---

# Research — Enterprise auth do DNA Cloud — SSO (SAML+OIDC) + SCIM pra multinacionais

Methodology: web-search-curated · 0 sources · 5 findings.

This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
