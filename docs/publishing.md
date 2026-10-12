# Publishing the client to PyPI

The client lives in `cli/` and is published as `bob-skills` on PyPI (first release 0.1.0 on 2026-09-10) so that `uvx bob-skills add <pack>` works on any machine. Without PyPI access, install it from the repository with `uv tool install "git+https://github.com/AlexandraIourenkova/bob-skills-marketplace.git#subdirectory=cli"`.

## Once: account and token

1. Create a PyPI account (https://pypi.org/account/register/) and enable two-factor authentication.
2. Create an API token at https://pypi.org/manage/account/token/. For the first upload the scope must be "Entire account" (the project does not exist yet); afterwards create a project-scoped token and delete the first one.
3. Keep the token in a password manager or in `~/.pypirc`; never paste it into a chat or a commit.

## Every release

```bash
cd cli
rm -rf dist
uv build                                  # dist/bob_skills-<version>.tar.gz and .whl
uvx twine check dist/*                    # metadata and README render
uv publish --token "$PYPI_TOKEN"          # or: uv publish, then answer the prompt with __token__ and the token
```

Bump `version` in `cli/pyproject.toml` and `cli/src/bob_skills/__init__.py` before building; PyPI never accepts the same version twice.

Check the result: `uvx --refresh bob-skills@<version> --version` on a clean machine.

## Optional: TestPyPI first

```bash
uv publish --publish-url https://test.pypi.org/legacy/ --token "$TEST_PYPI_TOKEN"
uvx --index https://test.pypi.org/simple/ --index-strategy unsafe-best-match bob-skills --version
```
