# Releasing DNA

Releases are **tag-triggered**: pushing a `vX.Y.Z` tag runs
[`.github/workflows/release.yml`](.github/workflows/release.yml), which
builds and publishes `dna-sdk` + `dna-cli` to PyPI and `dna-sdk` to npm.
Nothing publishes from PRs or branch pushes.

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

5. The `release` workflow does the rest:
   `sanity` (tag == versions) → `build-py` (`uv build` sdist+wheel for both
   Python packages, one artifact each) → `publish-pypi-sdk` +
   `publish-pypi-cli` (trusted publishing, OIDC — one job/environment per
   package) and `publish-npm` (`bun run build` + `npm publish --provenance`).

## One-time account prerequisites (repo owner)

The workflow is ready, but publishing only works after these are configured:

### PyPI — trusted publishing (no token)

Add a **pending publisher** for **each** project at
<https://pypi.org/manage/account/publishing/>. PyPI accepts a given
owner+repo+workflow+**environment** combination for only ONE project name,
so each package gets its own environment:

| Field | `dna-sdk` | `dna-cli` |
|---|---|---|
| PyPI project name | `dna-sdk` | `dna-cli` |
| Owner | `ruinosus` | `ruinosus` |
| Repository name | `dna` | `dna` |
| Workflow name | `release.yml` | `release.yml` |
| Environment name | `pypi` | `pypi-cli` |

Also create the two matching **GitHub environments** — `pypi` and `pypi-cli`
(Settings → Environments → New environment). Optional but recommended:
require a reviewer on them, making every publish a click-to-approve.

### npm — granular token (first publish)

npm trusted publishing (OIDC) can only be enabled on a package that already
exists, so the **first** publish authenticates with a token:

1. Create a **granular access token** at npmjs.com (Access Tokens → Generate
   → Granular) with **Read and write** permission, scoped to new/`dna-sdk`
   package only, with an expiry.
2. Save it as the repo secret **`NPM_TOKEN`**
   (Settings → Secrets and variables → Actions → New repository secret).

**Follow-up after `v0.1.0` is live:** configure trusted publishing on the
`dna-sdk` npm package (package Settings → Publishing access), switch the
workflow's publish step to OIDC, and revoke the token.

## After the workflow goes green

- Verify the three registry pages: [PyPI dna-sdk](https://pypi.org/project/dna-sdk/)
  · [PyPI dna-cli](https://pypi.org/project/dna-cli/)
  · [npm dna-sdk](https://www.npmjs.com/package/dna-sdk).
- Smoke the published artifacts in a scratch dir:
  `pip install dna-sdk dna-cli && dna --help` and
  `npm init -y && npm i dna-sdk && node -e "import('dna-sdk').then(m => console.log(!!m.Kernel))"`.
- Create the GitHub Release from the tag, pasting the CHANGELOG section.
