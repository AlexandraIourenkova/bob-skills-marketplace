# Who sees which usage report

| Report | Command | Who gets it |
|---|---|---|
| Whole account, per service | `ibmcloud billing account-usage` | Viewer or higher on the Billing service. The CLI help says "account admin only" |
| One resource group, per service | `ibmcloud billing resource-group-usage <group>` | Administrator of that group, or Billing access for the account |
| Per instance | `ibmcloud billing resource-instances-usage` | Viewer or higher on the Billing service; with `-g <group>` it narrows to one group |

A federated user's roles come from the access groups the account administrator put them in. To get the account view, ask the administrator for Viewer on the Billing service; to get one group, ask to be administrator of that group, which also grants changes in it and may be more than the user wants.

## Reading the refusal

The script turns a refusal into a line such as:

```
account usage for 2026-09 not available: needs Viewer or higher on the Billing service for the account
```

It never retries with other credentials and never asks the user for them.
