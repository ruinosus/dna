# Releasing DNA

Releases are **tag-triggered**: pushing a `vX.Y.Z` tag runs
[`.github/workflows/release.yml`](.github/workflows/release.yml) (PyPI
`dna-sdk`) and
[`.github/workflows/release-cli.yml`](.github/workflows/release-cli.yml)
(PyPI `dna-cli`). Nothing publishes from PRs or branch pushes.

> **Why two workflow files?** PyPI deduplicates trusted-publishing pending
> publishers on the full identity tuple — owner + repo + **workflow
> filename** + environment — and a tuple can be registered for only one
> project name. `dna-sdk` and `dna-cli` therefore publish from different
> workflow files (and different environments).

## Cutting a release

1. **Bump the version** — the same `X.Y.Z` in all manifests
   (the workflow's `sanity` job fails loud on any mismatch):
   - `packages/sdk-py/pyproject.toml` → `version`
   - `packages/cli/pyproject.toml` → `version`
   - `packages/client-py/pyproject.toml` → `version` *(once client publishing is enabled — see below)*
   - `packages/client-ts/package.json` → `version` *(idem)*
2. **Update `CHANGELOG.md`** — move the `[Unreleased]` content into a new
   `## [X.Y.Z] - YYYY-MM-DD` section and refresh the comparison links at the
   bottom.
3. **Merge to `main`** via PR (all CI checks green).
4. **Tag and push**:

   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```

5. The two workflows do the rest, each gated by the same `sanity` job
   (tag == every package version):
   - `release`: `build-py` (`uv build` sdist+wheel for dna-sdk) →
     `publish-pypi` (trusted publishing, environment `pypi`).
   - `release-cli`: `build-cli` → `publish-pypi-cli` (trusted publishing,
     environment `pypi-cli`).

## One-time account prerequisites (repo owner)

The workflows are ready, but publishing only works after these are configured:

### PyPI — trusted publishing (no token)

Add a **pending publisher** for **each** project at
<https://pypi.org/manage/account/publishing/>. Because of the
filename-in-the-identity dedup rule above, each package points at its own
workflow file + environment:

| Field | `dna-sdk` *(already configured)* | `dna-cli` |
|---|---|---|
| PyPI project name | `dna-sdk` | `dna-cli` |
| Owner | `ruinosus` | `ruinosus` |
| Repository name | `dna` | `dna` |
| Workflow name | `release.yml` | `release-cli.yml` |
| Environment name | `pypi` | `pypi-cli` |

Also create the two matching **GitHub environments** — `pypi` and `pypi-cli`
(Settings → Environments → New environment). Optional but recommended:
require a reviewer on them, making every publish a click-to-approve.

> **The `dna-sdk` npm package is retired.** It was the TypeScript SDK
> (`packages/sdk-ts`), frozen at the tag `sdk-ts-final`; `release.yml` no
> longer has a `publish-npm` job. TypeScript's package in this repo is now
> `dna-client` — see below.

## The DNA API clients (`dna-client` — PyPI + npm)

The official REST clients (`packages/client-py`, `packages/client-ts`) publish
from [`.github/workflows/release-client.yml`](.github/workflows/release-client.yml)
(PyPI `dna-client` env `pypi-client`, npm `dna-client`), tag-triggered like the
others. They are generated from `docs/openapi.json`; keep their versions in lock
step with the tag (the workflow's `sanity` job enforces it).

> **DORMANT until enabled.** This is a NEW package line, so publishing needs a
> one-time account setup only the repo owner can do. Until it is done, the whole
> `release-client` workflow is **gated off** by the repo variable
> `DNA_CLIENT_PUBLISH` — every job is a no-op unless it equals `true`, so a
> release tag never reds on the client jobs while the setup is pending. The
> build jobs are CI-verified (`typescript.yml` `client-ts` + `python.yml`
> `client-py`) and smoke-built locally when the feature landed.

**To enable client publishing (the human follow-up for `f-dna-client`):**

1. **PyPI** — add a pending publisher at
   <https://pypi.org/manage/account/publishing/>:

   | Field | `dna-client` (Python) |
   |---|---|
   | PyPI project name | `dna-client` |
   | Owner / Repo | `ruinosus` / `dna` |
   | Workflow name | `release-client.yml` |
   | Environment name | `pypi-client` |

   Then create the matching **GitHub environment** `pypi-client`
   (Settings → Environments → New environment).
2. **npm** — do the first `dna-client` publish manually (OIDC can only be
   configured on an existing package), then set its Trusted Publisher:

   ```bash
   cd packages/client-ts
   bun install --frozen-lockfile && bun run build
   npm login && npm publish --access public
   ```

   On npmjs.com: package `dna-client` → Settings → Trusted Publisher →
   repository `ruinosus/dna`, workflow `release-client.yml`.
3. **Flip the gate** — set the repo variable `DNA_CLIENT_PUBLISH=true`
   (Settings → Secrets and variables → Actions → Variables). From the next tag,
   `release-client` runs its `sanity → build → publish` jobs like the others
   (the npm guard skips a version already on the registry, so the manual
   first-publish tag stays green).

## After the workflows go green

- Verify the registry pages: [PyPI dna-sdk](https://pypi.org/project/dna-sdk/)
  · [PyPI dna-cli](https://pypi.org/project/dna-cli/).
- Smoke the published artifacts in a scratch dir:
  `pip install dna-sdk dna-cli && dna --help`.
- Create the GitHub Release from the tag, pasting the CHANGELOG section.
