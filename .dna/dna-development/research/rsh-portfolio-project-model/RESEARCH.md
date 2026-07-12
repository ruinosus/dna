---
apiVersion: github.com/ruinosus/dna/sdlc/v1
kind: Research
metadata:
  name: rsh-portfolio-project-model
spec:
  title: Modelo Org→Project→Repos do DNA Cloud — padroes de mercado (GitHub/GitLab/ADO/Jira/Linear)
  status: published
  objective: Ancorar o modelo de dados/permissao do console de portfolio do DNA Cloud nos padroes que
    GitHub/GitLab/Azure DevOps/Jira/Linear ja padronizaram, pra ser familiar e escalar em org. Suporta
    adr-portfolio-project-model + e-portfolio-console.
  methodology: web-search-curated
  executive_summary: |
    O mercado NAO padronizou UMA hierarquia, e a divisao e a historia toda. Dois modelos
    incompativeis: (a) Azure DevOps — Organization -> Project -> muitos Repos, onde um Project e
    um container explicito que segura N repos + boards + work-items sob UMA fronteira de permissao;
    (b) GitHub/GitLab — 'project' ou e um board que atravessa repos mas NAO os possui (GitHub
    Projects v2, repos direto sob a Org), ou e literalmente sinonimo de UM repo (GitLab). Azure
    DevOps e o encaixe exato pro 'um Project, muitos repos + board + inteligencia' do DNA Cloud;
    a Microsoft recomenda single-project-many-repos como default. RBAC convergiu numa escada
    ordenada (Guest/Read -> Owner/Admin), org-role herda pra baixo e sobrepoe resource-role,
    highest-role-wins, org-owner superuser. A DECISAO no1: Project como container multi-repo de
    primeira classe (modelo ADO), NAO colapsar em 1-repo-1-projeto (a armadilha GitLab).
    Decidido com o Barna: relacao repo<->project e N—N (repo pode estar em varios projetos);
    topo chamado 'Organization'.
  findings:
  - id: f-ado-container
    title: 'Azure DevOps (Org -> Project -> N Repos) e o modelo canonico pro ''um Project, muitos repos
      + board'': o Project e o container que possui board+work-items, repos herdam sua permissao'
    evidence_rating: evidence-based
  - id: f-github-no-container
    title: GitHub NAO tem container multi-repo (repos direto sob a Org; Projects v2 e board que atravessa
      repos mas nao os possui) — valida o board cross-repo, nao o container
    evidence_rating: evidence-based
  - id: f-gitlab-trap
    title: GitLab 'Project' = UM repo (grouping via Groups/Subgroups) — a armadilha 1-repo-1-projeto que
      o DNA Cloud tem que evitar
    evidence_rating: evidence-based
  - id: f-rbac-ladder
    title: RBAC padrao = escada ordenada (Guest -> Member -> Admin -> Owner), org-role herda pra baixo,
      highest-role-wins, org-owner superuser — vocabulario que passa em procurement
    evidence_rating: evidence-based
  - id: f-nn-decided
    title: 'Fork resolvido (Barna): repo<->project e N—N (repo compartilhavel entre projetos); ADO usa
      1—N, mas o caso de portfolio pede repo em varios projetos sem duplicar'
    evidence_rating: opinion-practice
  recommendations:
  - id: rec-project-container
    priority: high
    summary: Adotar Project como container multi-repo de primeira classe (modelo ADO). O Project e dono
      do board (scope SDLC) + IntelSources + memoria; repos anexados por referencia.
  - id: rec-nn-repos
    priority: high
    summary: 'Relacao Repo<->Project N—N (decidido): um repo pode ser anexado a varios projetos sem duplicar.
      Project e a fronteira de permissao; repo herda das que o referenciam.'
  - id: rec-org-naming
    priority: medium
    summary: Topo = 'Organization' (decidido) — familiar pro comprador enterprise (GitHub/ADO). Escada
      Owner/Admin/Member/Guest + highest-role-wins + org-owner superuser.
  - id: rec-entities
    priority: high
    summary: 'Entidades: Organization (tenant) · Membership(user,org,role) · Project · Repo/Source (N—N
      com Project) · ProjectMembership(user,project,role) · Role (escada). Portfolio = agregacao dos Projects
      da Org.'
  created_at: '2026-07-12T22:36:47+00:00'
  updated_at: '2026-07-12T22:36:47+00:00'
---

# Research — Modelo Org→Project→Repos do DNA Cloud — padroes de mercado (GitHub/GitLab/ADO/Jira/Linear)

Methodology: web-search-curated · 0 sources · 5 findings.

This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
