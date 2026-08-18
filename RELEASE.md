# Release runbook

## Prerequisites (one-time setup)

- A `pypi` GitHub Actions environment configured with a [PyPI Trusted Publisher](https://docs.pypi.org/trusted-publishers/)
  for this repository and the `release.yml` workflow, plus a `test-pypi` environment with the
  equivalent Trusted Publisher on Test PyPI. Both use OIDC — no API token is stored in GitHub.
- The very first upload to Test PyPI for this package name must be done **manually**
  (`python -m build && twine upload --repository testpypi dist/*`), because Test PyPI only accepts
  Trusted Publisher OIDC claims for a project once the project exists there. Once that manual
  upload succeeds, the automated `publish-test-pypi` job can publish every release after.
- The MCP registry listing is published via `mcp-publisher`, authenticating with GitHub OIDC
  (`mcp-publisher login github-oidc`) — no stored registry token either.

## Cutting a release

1. Bump the version in `pyproject.toml` (`[project].version`) and in `server.json` (both the
   top-level `version` and each entry under `packages[].version`). They must all match.
2. Open a PR with just the version bump, get it merged to `main`. CI's `registry-manifest` job
   fails the PR if `server.json` and `pyproject.toml` disagree.
3. On `main`, tag the merge commit with `v<version>`, e.g. `git tag v0.2.0 && git push origin v0.2.0`.
4. Pushing the tag triggers `.github/workflows/release.yml`:
   - `check-version` fails the whole run before anything is built or published if the tag
     (`v<version>`) doesn't match `pyproject.toml`'s version. Fix the tag or the version and
     re-tag rather than trying to reuse the same version number — PyPI never allows re-uploading
     a version.
   - `build` builds the sdist and wheel and runs `twine check` on them.
   - `publish-test-pypi` uploads the same artifacts to Test PyPI as a dry run, using OIDC
     (`skip-existing: true` so re-running after a partial failure doesn't error on an artifact
     that already made it to Test PyPI).
   - `publish-pypi` uploads to real PyPI, only after the Test PyPI dry run succeeds.
   - `publish-registry` publishes the updated `server.json` to the MCP registry, only after the
     PyPI upload succeeds.

## What to check after a release

- `pip install cal-auto-python==<version>` from a clean environment installs and
  `cal-auto-python --version` reports the right version.
- The listing at the MCP registry shows the new version and points at the package that was just
  published.

## When a step fails

- **`check-version` fails**: nothing was built or published. Fix the mismatch between the tag and
  `pyproject.toml`, delete the bad tag (`git push --delete origin v<bad>`), and re-tag.
- **`build` or `publish-test-pypi` fails**: nothing has reached real PyPI or the registry yet. Fix
  the problem, delete the tag, and re-tag — no version has been burned.
- **`publish-pypi` fails**: the package may or may not have landed on PyPI, but the registry
  listing has not been updated yet, so it's safe to leave as-is while you investigate. Because
  PyPI never allows overwriting a version, if the upload partially succeeded you cannot retry the
  same version — bump to the next version and start over. If it failed cleanly before anything
  uploaded, fix the issue and re-run the `release.yml` workflow for the same tag instead of
  re-tagging.
- **`publish-registry` fails**: the package is already on PyPI, so do not re-run `publish-pypi`.
  Fix the registry problem and re-run just the `publish-registry` job for the same workflow run
  (or run `mcp-publisher publish` manually from a checkout at that tag).
