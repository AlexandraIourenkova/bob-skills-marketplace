# Pack `redhat-openshift` — OpenShift updates and GitOps by Red Hat

Vendor: `redhat` (an IBM company). Curated from [openshift/agentic-skills](https://github.com/openshift/agentic-skills) (Apache-2.0), the skills OpenShift maintainers publish for OpenShift Lightspeed, at commit `da1431b482a4`. Install with `uvx bob-skills add redhat-openshift`, or with `/skills-add redhat-openshift` inside Bob once bob-essentials is installed.

## Before you install

**argo-operations and argo-team-onboard install Argo CD, create, sync and roll back Applications and apply AppProjects, RBAC and cluster Secrets; a few reference procedures apply CRDs or remote manifests before their own confirmation step, and the argocd-rbac-cm example replaces the whole policy.**

Covered by: Both skills preview with a server-side dry run and ask before applying. The pack rule adds a yes per command with the kube context named, pinned remote manifests, and a merge instead of the rbac example. cluster-update-advisor only advises and never upgrades.

**Logs, events, Application status, readiness JSON and manifests from Git reach Bob as they are, and none of the skills says to treat them as data.**

Covered by: The pack rule and the bob-essentials security-defaults rule make that content data, never instructions; runbooks are read, not executed.

**Backup steps write repo and cluster Secrets to local files as plain base64, some steps print Secrets or put tokens on the command line, and the repo audit can copy secret values into its report.**

Covered by: The pack rule forbids printing Secrets, keeps tokens off command lines and output, asks before a backup with Secrets is written to disk, and redacts secret values in audit reports.

**argo-operations starts the Argo Rollouts dashboard in the background; it has no authentication and acts with your cluster login.**

Covered by: The pack rule says not to start it or a port-forward on all interfaces, and to bind 127.0.0.1 when you ask for one.

| Skill | What it adds |
|---|---|
| `cluster-update-advisor` | Reads cluster update readiness data and returns recommend, warn, block or escalate with the blockers and warnings found |
| `product-lifecycle` | Support phases, end-of-life dates and OpenShift compatibility from Red Hat's public Product Life Cycle API, one product or a batch of OLM operators |
| `argo-knowledge` | Reference for Argo CD, ApplicationSets, Rollouts, Workflows, Events, notifications and GitOps Promoter, with ten YAML patterns |
| `argo-cluster-debug` | Read-first debugging of failing, stuck or degraded Argo resources on a live cluster, ending in a root-cause report |
| `argo-repo-audit` | Audit of a local GitOps repository: repository pattern, best practices, security, and schema validation with kubeconform |
| `argo-operations` | Install, deploy, sync, promote, roll back, upgrade and back up Argo, with a dry run and a yes before every write |
| `argo-team-onboard` | A scoped AppProject, Applications and RBAC for a new team, or a self-service ApplicationSet driven by `teams.yaml` |
| `rules/openshift.md` | Our rule for this pack: cluster and Git content is data, one yes per change after a preview, no printed Secrets or tokens, pinned remote installs |

## Before you use it

- The cluster skills use your own `oc` or `kubectl` login and the `argocd` CLI, so they can do whatever your account can. Run them with a read-only account when you only need answers.
- `cluster-update-advisor` was written for OpenShift Lightspeed, where the Cluster Version Operator hands it readiness JSON. Without that JSON it answers escalate. It names `prometheus`, `jira` and `redhat-support` skills that do not exist in the source repository.
- `product-lifecycle` needs `--ocp` as major.minor (`4.21`): the script matches the version string exactly.
- `argo-repo-audit` validation needs `yq`, `kubeconform` and `kustomize`. `kustomize build` fetches any remote bases the audited repository lists.

## Not included

- `investigate-alert`: its Prometheus scripts call Thanos with TLS verification off (`wget --no-check-certificate`), pass your OAuth token on the command line, and print it from `prometheus-setup.sh`. It joins the pack once that is fixed upstream.
- `kubernetes-docs` and `openshift-docs`: 84 MB of converted documentation.
- `find-token`: a fixture for the upstream eval harness, not a skill for users.
- The `evals/` folder of each GitOps skill: its prompts point at fixture repositories that are not in the skill, and one plants a fake password for the audit to find (`source.exclude` in `pack.json`).

Refresh with `python3 scripts/sync_upstream.py redhat-openshift`, then `bob-skills registry validate --fix`, lint, scanners, version bump, PR, tag.
