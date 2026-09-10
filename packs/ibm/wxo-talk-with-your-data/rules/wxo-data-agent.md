# Data agents on watsonx Orchestrate

These rules apply when building a text-to-SQL or data agent for watsonx Orchestrate from a spreadsheet or a database.

## Environment

- Install the ADK in a dedicated virtual environment (`uv venv .venv-wxo && uv pip install --python .venv-wxo ibm-watsonx-orchestrate`). Never add `ibm-watsonx-orchestrate` to a tool's `requirements.txt`; the platform provides it.
- Run `orchestrate settings set-encoding utf-8` before importing YAML that contains Hebrew, Cyrillic or accented text; without it the ADK corrupts the text.
- Check the active environment with `orchestrate env list` before importing. Confirm the environment with the user when it is not obvious.

## Data

- For a prototype, bundle the data as SQLite inside the Python tool. Do not deploy an external database until the user asks for one.
- Never commit customer data files or generated SQLite databases to a repository; keep them in the project's `data/` folder listed in `.gitignore`.
- Put the table schema and a few sample questions into the agent instructions, so the agent writes correct SQL without exploring the database first.

## Demo page

- Serve the demo page locally and verify the chat works end to end before showing it. Embed snippets come from the Orchestrate UI; never paste an API key into the page.
- Search the documentation with the `watsonx-orchestrate-adk-docs` MCP server before changing the embed configuration; the widget options change between releases.
