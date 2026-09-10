# Vendor onboarding

One vendor per product, and that vendor is the product's owner. Users do not publish; they request. The marketplace team curates packs from each vendor's official repositories (recording source, ref and checksums) until the vendor enrols its own maintainers. A vendor is listed only when at least one pack is curated from its official repository under a licence that allows redistribution. At the start: IBM, Anthropic, OpenAI, Google, HashiCorp and Microsoft.

## Requesting a pack

Open an issue with the **Request a pack** template. It names the product, the vendor organisation and what the pack should contain; the marketplace team forwards it to the vendor.

## Enrolling a vendor

1. PR adding an entry to `vendors.json`: id, display name, GitHub host and organisation, maintainers (logins on this GitHub host), security contact, network allow-list, public key (or `null` until a cosign key exists).
2. Same PR adds `/packs/<vendor-id>/  @maintainer1 @maintainer2` to `CODEOWNERS`.
3. Two marketplace administrators approve. Once the administrators have keys, `vendors.json` also carries their signature.

## Publishing the first pack

1. Create `packs/<vendor-id>/<pack>/` with `pack.json`, `skills/`, and any rules, commands or modes. Follow [pack-format.md](pack-format.md). For a pack curated from an upstream repository, fill `source` (repo, ref, path) and the `skills` list, then run `python3 scripts/sync_upstream.py <pack>`: it copies the skills, the licence, and pins `source.ref` to the exact commit. Only skills under a licence that allows redistribution (Apache-2.0, MIT, MPL-2.0) are eligible.
2. Run locally:

   ```bash
   uv run --project cli bob-skills registry validate --fix
   uv run --project cli bob-skills lint packs/<vendor-id>/<pack>
   ```

3. Read every linter finding. Fix what is real; for accepted false positives run `lint ... --write-baseline --reason "..."` and edit the reasons. Then run the scanners, `python3 scripts/run_scanners.py <pack> --reports reports`, read the reports, and accept what you reviewed with `--accept-skillspector "<reason>" --accept-cisco "<reason>" --write`.
4. Open the PR from a maintainer account. CI checks the author, runs the gate, and posts the SARIF report.
5. A vendor maintainer and a marketplace administrator approve after reading the SKILL.md diff.
6. After the merge, tag the commit `<pack>--v<version>` and push the tag. The release workflow verifies the tag against `pack.json`, rebuilds the index and publishes the release.

## Releasing a new version

Bump `version` in `pack.json`, refresh checksums with `validate --fix`, PR, two approvals, tag. `bob-skills update` shows users the SKILL.md diff between the versions.

## Revoking a version

Add the version to `revokedVersions` in `pack.json` and release a fixed version in the same PR when possible. The installer refuses the revoked version, `update` tells users, and the guard refuses skills of that version.
