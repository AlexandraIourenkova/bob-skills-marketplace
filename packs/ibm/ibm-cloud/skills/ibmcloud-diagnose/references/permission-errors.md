# "Not authorized" from the CLI

A 403, "not authorized", "forbidden" or "does not have access" means the session is open but the user's access policies do not cover the request. The pack never asks for more access on the user's behalf and never switches to another identity to get around it.

## What to tell the user

1. Which command was refused, in which account and region.
2. Which role usually covers it (table below).
3. That the account administrator grants it, typically by adding the user to an access group. A federated user's rights come from that access group, not from the user's own profile.

| Refused command | Role that usually covers it |
|---|---|
| `ibmcloud resource service-instances`, `resource search` | Viewer platform role on the resource group, or on the services in it. Search shows only what the user can see; an empty result can mean no access rather than no resources |
| `ibmcloud is ...` (VPC reads) | Viewer platform role on VPC Infrastructure Services |
| `ibmcloud ks cluster get`, `ks worker ls` | Viewer platform role on Kubernetes Service for that cluster or its resource group |
| `ibmcloud ce app get`, `app events`, `app logs` | Viewer platform role and Reader service role on the Code Engine project |
| `ibmcloud billing account-usage` | Viewer or higher on the Billing service; the CLI help calls it account admin |
| `ibmcloud billing resource-group-usage <group>` | Administrator of that resource group, or Billing access |

## Checking what the user can do

The user sees their own access groups in the console under Manage > Access (IAM) > Users, or with:

```bash
ibmcloud iam access-groups
```

Listing another user's policies needs administrator rights; the access review in a later version of this pack covers that.
