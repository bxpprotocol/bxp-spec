# Releasing BXP

Everything here is verified by `make verify-packages`, which builds both
distributions, installs them into clean environments, imports them, and runs
the console script. Run it before every publish. **Both packages used to build
into empty artefacts** — the wheel contained no modules and the npm tarball
contained only `package.json` — so this check exists because the failure mode is
silent: the install succeeds and the import does not.

---

## One-time setup

### PyPI

1. Create an account and a project API token at
   `https://pypi.org/manage/account/token/`. Scope it to the `bxp-sdk` project only.
2. Save it as a GitHub Actions secret: **Settings → Secrets and variables →
   Actions → New repository secret**, name `PYPI_API_TOKEN`.
3. Optionally use [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
   instead of a token, which removes the long-lived secret entirely.

### npm

1. Create an automation token at
   `https://www.npmjs.com/settings/access-tokens` with publish scope.
2. Save it as a repository secret named `NPM_TOKEN`.
3. `npm login --registry=https://registry.npmjs.org` for local publishing.

### GitHub Packages (container registry)

1. Create a classic PAT with `write:packages` at
   `https://github.com/settings/tokens`.
2. Save it as `GHCR_TOKEN`.
3. The package must be named `ghcr.io/bxpprotocol/bxp-spec`. Change the
   `ghcr.io/${{ github.repository }}` reference in the workflow if the org or
   repository name differs.

---

## Publishing a release

```bash
# 1. Verify the artefacts are actually publishable
make verify-packages

# 2. Confirm the working tree is clean and tests pass
make ci-local

# 3. Tag the release. The tag is what triggers publication.
git tag -a v2.1.0 -m "Release notes"
git push origin v2.1.0

# 4. Create the GitHub Release. The `on: release: published` trigger fires the
#    publish job. Creating the tag alone does not.
gh release create v2.1.0 --title "v2.1.0" --notes-file RELEASE_NOTES.md
```

If `gh` is not installed, create the release through the GitHub UI: **Releases →
Draft a new release → choose the existing tag**. Either path fires the workflow.

### What the workflow does

| Job | Registry | Triggered by |
|---|---|---|
| `build` | — | every push; builds the wheel, installs it in a venv, imports it |
| `publish` | PyPI + npm | GitHub Release published |
| Docker | GHCR | added separately, see below |

---

## Publishing the container

The CI file does not currently build the image. To add GHCR publishing, append
this job:

```yaml
  container:
    name: Publish container
    runs-on: ubuntu-latest
    needs: [build]
    if: github.event_name == 'release' && github.event.action == 'published'
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GHCR_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.ref_name }}
            ghcr.io/${{ github.repository }}:latest
```

---

## Publishing locally, for testing

Do not test a release on the real registries. Use TestPyPI and a scratch scope.

```bash
# TestPyPI
python -m twine upload --repository testpypi dist/*

# npm, using a scoped sandbox rather than @bxp/sdk
npm publish --dry-run          # always dry-run first
```

---

## Versioning

The protocol version and the SDK version move independently, and that is
intentional.

| Artefact | Version | Meaning |
|---|---|---|
| `SPEC.md` | 2.0 | The wire format. Frozen within major version 2. |
| `bxp-sdk` / `@bxp/sdk` | 2.1.x | Implementation version. May ship ahead of the spec. |
| Git tag | v2.1.0 | A release of this repository's software. |

A spec change that alters the wire format requires a new spec major version, 18
months of notice, and dual-version support (SPEC.md §12). Adding an optional
field, endpoint, or agent is a MINOR change and needs no coordination.

`scripts/check_docs.py` warns when the SDK version does not start with the
protocol version. That warning is expected while the SDK ships ahead of the
specification; it is not a failure.

---

## After publishing

1. Verify the packages resolve:
   ```bash
   pip install bxp-sdk && python -c "import bxp_sdk; print(bxp_sdk.__file__)"
   npm view @bxp/sdk version
   ```
2. Confirm the README install instructions now match reality.
3. Add the registry badges only after the packages resolve. A badge pointing at
   a non-existent package is a credibility cost, not a signal.
4. Tag the release in Wikidata once `RELEASE_NOTES.md` names the version.