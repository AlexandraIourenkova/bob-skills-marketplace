# Fixes for what the checks find

Every command on this page changes the account. Before running one:

1. Confirm the exact syntax for the user's CLI version with `--help` on that command (it only reads). The VPC plug-in in particular changes argument forms between versions.
2. Show the user the full command, the account and region, the resources it touches, and what it opens, restarts or replaces.
3. Run it only after the user says yes to that command. One yes covers one command.
4. Run the same check again and show that the FAIL turned into PASS.

Prefer the smallest change: one port, one source range, one worker.

## VPC: a port does not answer

| Finding | Fix | Notes |
|---|---|---|
| instance running: FAIL | `ibmcloud is instance-start <instance>` | Ask why it stopped first: `status_reasons` in the check output |
| public path: FAIL (inbound) | reserve a floating IP for the interface: `ibmcloud is floating-ip-reserve <name> --nic <interface-id>` | A floating IP exposes the VSI to the internet; confirm that is intended, or put a load balancer in front |
| public path: FAIL (outbound) | attach a public gateway to the subnet: `ibmcloud is subnet-update <subnet> --pgw <gateway>` | The gateway gives every VSI in the subnet outbound access |
| security group inbound: FAIL | `ibmcloud is security-group-rule-add <group> inbound tcp --port-min <port> --port-max <port> --remote <cidr>` | Use the narrowest source; `0.0.0.0/0` on 22 or 3389 is a finding, not a fix |
| network ACL in: FAIL | add an allow rule for the request before the deny that matched: `ibmcloud is network-acl-rule-add <acl> ... --before-rule-name <deny-rule>` | ACL rules are evaluated in order |
| network ACL reply out: FAIL | add an outbound allow for the reply: destination the client range, destination ports 1024-65535, source port the service port | ACLs are stateless; every inbound rule needs its reply rule |

## Kubernetes Service and OpenShift

| Finding | Fix | Notes |
|---|---|---|
| a worker is not ready | `ibmcloud ks worker reboot --cluster <cluster> --worker <worker>` | Least invasive first; drain workloads the user cares about |
| still not ready after a reboot | VPC clusters: `ibmcloud ks worker replace --cluster <cluster> --worker <worker>`; classic: `ibmcloud ks worker reload ...` | Replace recreates the worker: data on its local disk is gone |
| workers behind the master | VPC: `ibmcloud ks worker replace --cluster <cluster> --worker <worker> --update`, one worker at a time | Check the version is still supported: `ibmcloud ks versions` |
| update pending on the master | `ibmcloud ks cluster master update --cluster <cluster> --version <version>` | Read the version's change log first; masters do not roll back |
| Ingress warning | read `ibmcloud ks ingress status-report get --cluster <cluster>` first | Often a single worker or a certificate; fix the cause, not the router |

In-cluster work (pods, deployments, routes) belongs to the redhat-openshift pack or `oc` and `kubectl` directly.

## Code Engine

| Hint | Fix | Notes |
|---|---|---|
| the image cannot be pulled | check the reference and tag; for a private registry create a registry secret and attach it: `ibmcloud ce registry create --name <secret> --server <registry>` then `ibmcloud ce app update --name <app> --registry-secret <secret>` | The user types the registry password or API key at the prompt; never pass it on the command line |
| the registry refused the pull | recreate the registry secret with a key that can read the namespace | |
| does not answer on the port | `ibmcloud ce app update --name <app> --port <port>`, or make the app listen on the configured port on 0.0.0.0 | Default port 8080 |
| out of memory | `ibmcloud ce app update --name <app> --memory <size> --cpu <cpu>` | Memory and CPU come in fixed pairs; `--help` lists them |
| starts and exits | fix the app, rebuild, then `ibmcloud ce app update --name <app> --image <image:tag>` | Traffic stays on the last ready revision meanwhile |
| a quota is reached | scale down or delete apps the user names, or ask for a quota increase | Deleting is the user's decision about their own apps |
