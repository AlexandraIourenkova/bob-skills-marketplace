---
description: One read-only IBM Cloud report - setup check, inventory and this month's cost against the last - saved under ibmcloud-reports/ and summarised in the chat
argument-hint: [resource-group]
---

Make a read-only report of the IBM Cloud account for the resource group `$ARGUMENTS`, or the whole account when it is empty. Nothing in the account changes.

1. **Session.** Run `ibmcloud-setup/scripts/check_setup.py`. Without a session, tell the user how to log in and stop. Otherwise say the account, region and resource group, and wait until the user confirms it is the right account.
2. **Inventory.** Run `ibmcloud-inventory/scripts/inventory.py --out ibmcloud-reports/inventory`, adding `--group $ARGUMENTS` when a group was given.
3. **Cost.** Run `ibmcloud-cost/scripts/usage_report.py --compare --out ibmcloud-reports/cost`, adding `--group $ARGUMENTS` when a group was given.
4. **Summary**, in this order: account and scope; number of instances and the findings; total cost with the change against last month; top services and top instances; instances billed with zero usage; what the user's role did not allow and which role would.
5. **Offer** an xlsx workbook with an inventory sheet and a cost sheet through office-docs, or a short deck through the presentations pack when the report is going to be presented.
