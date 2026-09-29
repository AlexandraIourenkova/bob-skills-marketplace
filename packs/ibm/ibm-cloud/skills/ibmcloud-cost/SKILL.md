---
name: ibmcloud-cost
description: Show where the IBM Cloud money goes, read-only - cost per service, per resource group and per instance for a month, the change against the previous month, the top spenders, and instances billed while their usage is zero, from the IBM Cloud usage reports. Works with the role the user has - account billing access gives the whole account, a resource group administrator gets that group - and names the role needed for anything the role does not allow. Never stops, scales or deletes anything. Use for "how much do we spend on IBM Cloud", "why did the bill go up", "what costs the most", "cost by resource group", "cloud cost report", "сколько мы тратим в IBM Cloud", "почему вырос счёт", "расходы по группам ресурсов".
---

# ibmcloud-cost

Paths are relative to this skill folder. The script runs `ibmcloud billing account-usage`, `resource-group-usage` and `resource-instances-usage` with `--output json`, and writes only into its output folder. Make sure `ibmcloud-setup` reported a session and the user confirmed the account first.

## Steps

1. Run the report for this month against the previous one:

   ```bash
   python3 scripts/usage_report.py --compare --out ibmcloud-reports/cost
   ```

   Other months: `--month 2026-08`. The current month is month to date; say so when comparing.

2. If the account report is refused, the output names the role it needs. A user who administers a resource group still gets that group:

   ```bash
   python3 scripts/usage_report.py --compare --group <resource-group> --out ibmcloud-reports/cost
   ```

   When nothing is available, explain which role to ask for with `references/billing-roles.md`. Never look for another way into billing data.

3. Report back: the total and the change, the top services, the resource groups, the top instances, the biggest changes, and the instances billed with zero usage. Name the currency.

4. Offer a spreadsheet through the `xlsx` skill of office-docs from `cost-<month>.csv`, or a chart of cost by service with the presentations pack.

## Zero usage is a question, not a verdict

An instance billed while every usage quantity is zero is often reserved capacity, a paid plan nobody uses, or something left from a test. List it for review with its owner. Stopping, downsizing or deleting it changes the account: show the command, its target and what stops working, and run it only after the user says yes to that command.

## Limits

- Usage reports lag behind actual use by up to a day, and some services report only at month end.
- Costs are list prices after discounts the account has; credits and invoices are not included. For the invoice, the user opens Billing and usage in the console.
- Quotas and limits are not part of this report.
