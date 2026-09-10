<!-- Copyright contributors to the Agent Skills project -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- This file was authored with the assistance of AI Tool: Claude Code (Claude Opus) -->

# Airgapped / on-prem pre-flight checks

Load this only when the target topology is **airgapped or self-managed** (per
the architecture plan). For IBM Cloud SaaS tenants, skip it entirely.

Run these checks BEFORE the first `orchestrate ... import`, to confirm none of
your code or config will reach out to the public internet:

1. **`WO_INSTANCE` is an internal endpoint.** Confirm the URL resolves
   to the customer's internal network and is reachable from the build
   host. No `*.cloud.ibm.com` hostnames in `WO_INSTANCE` for an
   airgapped install.
2. **IAM endpoint is internally mirrored.** If the customer's WxO
   install brokers its own token issuance, your IAM call (Phase 4
   testing) must target that internal endpoint — `iam.cloud.ibm.com`
   is unreachable from airgapped clusters. Check the WxO install docs
   for the local IAM URL.
3. **No tool code calls public services.** `grep`-check tool Python
   for hardcoded `https://` URLs to public domains; everything should
   route via WxO connections (`app_id`) pointing at internal services.
4. **All referenced models are tenant-local.** Models named in your
   agent YAML must exist in `orchestrate models list` on the
   airgapped tenant. External model providers (`groq/`, `bedrock/`,
   public `watsonx/`) are unavailable unless explicitly mirrored
   inside the customer's environment.
5. **No outbound dependencies in `requirements.txt`.** Customer
   build hosts in airgapped environments cannot reach PyPI. Verify
   the customer maintains an internal mirror (e.g., Artifactory) and
   that `requirements.txt` pins to versions present in the mirror.

The internal endpoints and mirrors for these checks should be recorded in
the customer's `customer_environment_supplement.md` (§2), provided by the
platform team as part of Phase 1 approval. If that file is absent or §2 is
blank, ask before deploying — surprises in this layer are the most common
cause of "imported successfully but agent fails at first invocation" in
airgapped installs.
