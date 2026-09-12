# gitgraph

gitgraph is a personal terminal tool: point it at a folder, pick a git repo underneath, and browse `git log --graph --all` with the selected commit’s hash, date, subject, and author on screen.

Python 3.10+, `git` on PATH. Standard library only. No pip, no npm, no local server.

## Run (Windows)

From a clone of this repository:

```powershell
python gitgraph\gitgraph.py C:\src
```

Omit the path to scan the current directory. `--list` prints git roots and exits:

```powershell
python gitgraph\gitgraph.py --list C:\src
```

- Several repos: arrow keys (or j/k), Enter to open.
- One repo: opens the graph immediately.
- Graph: ↑↓ / j k, PageUp / PageDown. Highlight shows hash, date, subject, author.
- `q` quits.

History is capped at 400 commits (`--limit`) so a large `--all` graph does not freeze. Nested `.git` directories are found; `node_modules`, `.venv`, `dist`, and similar trees are skipped. Read-only: no checkout, no rebase.

## Tests

```powershell
cd gitgraph
python test_gitgraph.py
```

## Status

Public personal prototype. Works in a real terminal (Windows console VT, or Unix). Not a product, not a replacement for lazygit.

## License

MIT. See `LICENSE`.
