# Releasing DNA

Releases are **tag-triggered**: pushing a `vX.Y.Z` tag runs
[`.github/workflows/release.yml`](.github/workflows/release.yml) (PyPI
`dna-sdk` + npm `dna-sdk`) and
[`.github/workflows/release-cli.yml`](.github/workflows/release-cli.yml)
(PyPI `dna-cli`). Nothing publishes from PRs or branch pushes.

> **Why two workflow files?** PyPI deduplicates trusted-publishing pending
> publishers on the full identity tuple — owner + repo + **workflow
> filename** + environment — and a tuple can be registered for only one
> project name. `dna-sdk` and `dna-cli` therefore publish from different
> workflow files (and different environments).

## Cutting a release

1. **Bump the version** — the same `X.Y.Z` in all three manifests
   (the workflow's `sanity` job fails loud on any mismatch):
   - `packages/sdk-py/pyproject.toml` → `version`
   - `packages/cli/pyproject.toml` → `version`
   - `packages/sdk-ts/package.json` → `version`
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
     `publish-pypi` (trusted publishing, environment `pypi`), plus
     `publish-npm` (`bun run build` + `npm publish --provenance` via npm
     OIDC trusted publishing — skipped automatically if the tag's version
     is already on the registry).
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

### npm — manual first publish, then OIDC (no token, no secret)

npm trusted publishing (OIDC) can only be configured on a package that
already exists, so the **first** `dna-sdk` publish is done locally by the
owner — no `NPM_TOKEN`, no repo secret, ever:

1. Build and publish from the repo:

   ```bash
   cd packages/sdk-ts
   bun install --frozen-lockfile && bun run build
   npm login
   npm publish --access public
   ```

2. Once the package exists on npmjs.com, configure the **Trusted
   Publisher** on its settings page (package → Settings → Trusted
   Publisher): repository `ruinosus/dna`, workflow `release.yml`.

From then on the `publish-npm` job publishes tokenlessly via OIDC
(`npm publish --provenance`, npm >= 11.5.1 on the runner); its guard step
skips the publish when the tag's version is already on the registry — so
running the `v0.1.0` tag after the manual publish stays green.

## After the workflows go green

- Verify the three registry pages: [PyPI dna-sdk](https://pypi.org/project/dna-sdk/)
  · [PyPI dna-cli](https://pypi.org/project/dna-cli/)
  · [npm dna-sdk](https://www.npmjs.com/package/dna-sdk).
- Smoke the published artifacts in a scratch dir:
  `pip install dna-sdk dna-cli && dna --help` and
  `npm init -y && npm i dna-sdk && node -e "import('dna-sdk').then(m => console.log(!!m.Kernel))"`.
- Create the GitHub Release from the tag, pasting the CHANGELOG section.
