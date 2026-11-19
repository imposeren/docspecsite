# docspecsite

docspecsite checks a repo's docs and renders every version of every doc from git history to a static site.
It is the tool behind the [docs-driven template](https://github.com/imposeren/docs-driven-template): projects keep their spec as Markdown docs with front matter in `docs/`, and docspecsite enforces the template's rules and shows each doc with its own history.

- `docspecsite check` — front matter, ADR file names, links, `index.md` children lists, file names, and no deleted or renamed docs.
- `docspecsite list` / `docspecsite backlinks` — find docs by front matter, and the docs that link to a doc, without rendering.
- `docspecsite build` — a static site with a page, a diff and a version picker for every version of every doc, loud old-version warnings, version-aware links, tag, component and status indexes, and a code reference generated from Python code.

## Use it in a project

A project pins one release tag (`vX.Y.Z` below: use the latest [release tag](https://github.com/imposeren/docspecsite/tags)) in two places:

- `.pre-commit-config.yaml` — the `docs-check` hook runs `docspecsite check --staged` on every commit:

  ```yaml
  - repo: https://github.com/imposeren/docspecsite
    rev: vX.Y.Z
    hooks:
      - id: docs-check
  ```

- `compose.yaml` — a `docs` service built from this repo at the same tag, with the project's repo mounted at `/repo`:

  ```yaml
  services:
    docs:
      build:
        context: https://github.com/imposeren/docspecsite.git#vX.Y.Z
      user: "${UID:-1000}:${GID:-1000}"
      volumes:
        - .:/repo
  ```

  Then `docker compose run --rm docs build` writes the site to `./site`.

Settings live in `docspecsite.toml` at the project's root (`adr-prefix`, `source-url`, `code-dirs`, `code-components`, `toc-min-headings`).
Projects started from the template have all of this already.
The full guide: [docs/guides/using-docspecsite.md](docs/guides/using-docspecsite.md).

## Docs

docspecsite is itself docs-driven: its spec is in [docs/](docs/index.md).
Start with [what it does](docs/behavior/index.md), [its commands](docs/behavior/commands.md) and [how it works](docs/architecture/docs-tooling.md).

## Develop

With Docker (Compose v2), [uv](https://docs.astral.sh/uv/) (for the commit hooks) and [prek](https://github.com/j178/prek) installed:

```
docker compose build dev && uv sync && prek install
docker compose run --rm test
docker compose run --rm docs-check
```

The same runs natively with uv: `uv run pytest`, `uv run docspecsite check`.

Setup and daily use: [docs/guides/contributor-setup.md](docs/guides/contributor-setup.md).

## License

MIT, see [LICENSE](LICENSE).
