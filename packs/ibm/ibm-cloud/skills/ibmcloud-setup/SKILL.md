---
name: ibmcloud-setup
description: Check and prepare the IBM Cloud CLI before any IBM Cloud work - the CLI version, the plug-ins the ibm-cloud pack uses (VPC, Kubernetes Service, Code Engine), whether a session is open and which account, region and resource group it targets, and whether API tracing is on. Guides federated (SSO) login, where the user types the one-time passcode in their own terminal, and login with an API key from the environment. Use it first in any IBM Cloud task and whenever a command fails with "Not logged in", a missing plug-in or the wrong account. Triggers include "check my IBM Cloud setup", "log in to IBM Cloud", "which IBM Cloud account am I on", "ibmcloud says not logged in", "настрой ibmcloud", "в каком я аккаунте IBM Cloud".
---

# ibmcloud-setup

Paths are relative to this skill folder. The script only reads: it runs `ibmcloud version`, `ibmcloud plugin list` and `ibmcloud target`, looks at environment variables by name, and never logs in, installs or prints a key.

## Steps

1. Run the check:

   ```bash
   python3 scripts/check_setup.py
   ```

   Exit code 0 means ready: CLI present, plug-ins installed, session open. Anything else comes with numbered next steps.

2. **No session.** Logging in is the user's step; never ask for a passcode, password or key in the chat.
   - Federated account (company SSO): the user runs `ibmcloud login --sso` in their own terminal, opens the link, and types the one-time passcode there. Then run the check again.
   - API key: the user puts the key in `IBMCLOUD_API_KEY` in their shell and runs `ibmcloud login`; the CLI reads the variable itself. Never put a key on a command line, in a file in the project or in `.bob/mcp.json`.

3. **Confirm the target with the user** before any other IBM Cloud skill runs: say the account name and ID, the region and the resource group from the check, and ask whether that is the account they mean. Federated users often have several. Switching is a local change the user approves first:

   ```bash
   ibmcloud target -c <account-id> -r <region> -g <resource-group>
   ```

4. **Missing plug-ins.** Show the `ibmcloud plugin install <name>` line from the check and run it only after the user agrees: it installs software on their machine. Only the plug-ins for the checks they need are required.

5. **API tracing on.** `IBMCLOUD_TRACE` makes the CLI print API traffic, which can end up in logs and transcripts. The pack's scripts stop while it is on; ask the user to unset it in their shell.

6. Hand over: `ibmcloud-inventory` for what the account holds, `ibmcloud-diagnose` for something broken, `ibmcloud-cost` for the bill.

## Limits of this skill

- Never log in on the user's behalf, handle a passcode, or read `~/.bluemix` files: they hold the session tokens.
- Never use `--skip-ssl-validation` or an API endpoint over plain HTTP. If a certificate fails, stop and tell the user.
- Never run a command that changes the account from this skill. Everything here reads, or changes local configuration the user approved.
