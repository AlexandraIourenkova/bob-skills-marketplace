# watsonx.data integration rules

These rules apply to the IBM watsonx.data integration skills (flow lifecycle, DataStage, pyflow, run investigation, bug reports).

## The MCP server comes from the user's IBM Cloud account

- The skills call the Agentic Data Integration MCP server hosted on IBM Cloud. Its address and credentials belong to the user's watsonx.data integration instance and are not part of this pack.
- Before the first flow task, check that the server is connected (it should appear in Bob's MCP panel). If it is not, help the user register it: open the IBM documentation page "Integrating data with the MCP server" (https://www.ibm.com/docs/en/watsonx/wdi/saas?topic=integration-agentic-data), take the server URL and the authentication method from the user's instance, and add an entry to the project `.bob/mcp.json` of this shape, replacing the placeholders:

```json
{
  "mcpServers": {
    "watsonx-data-integration": {
      "type": "streamable-http",
      "url": "https://<your-instance-host>/<mcp-path>",
      "headers": { "Authorization": "Bearer <token from IBM Cloud IAM>" }
    }
  }
}
```

- Never write a real token into a file that is committed. Keep it in an environment variable or a local, git-ignored file and reference it from the config when Bob supports it.

## Working with flows

- Describe the data requirement, let the skill plan the flow, and show the plan to the user before creating or running anything.
- Running, scheduling or deleting a job changes the customer's environment: confirm the exact flow and project names with the user first.
- For failed runs, start with `di-agent-datastage-investigation` and produce a bug report with `di-agent-bug-report` only when the user asks for one.
