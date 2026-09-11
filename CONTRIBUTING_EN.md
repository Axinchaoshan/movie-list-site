# Contributing

Thanks for your interest in the Movie List Site Generator! Issues, suggestions, and PRs are all welcome.

## Reporting Issues

- **For bugs**, include: OS, Python version, full error output, and steps to reproduce.
- **For feature requests**, describe the use case and expected behavior.

## Submitting a PR

1. Fork the repo to your account.
2. Branch off `main`: `git checkout -b fix/xxx` or `feat/xxx`.
3. Test locally: after `pip install -r requirements.txt`, confirm `python gen_site.py` builds `site/`.
4. Commit, push, and open a Pull Request against `main` with a clear description of the change.

## ⚠️ Hard rules (must follow)

- **Never commit real cloud-drive links or your movie list.** The repo only accepts placeholder data (`data/example_movie_master.csv`). Keep real data out of git — inject it via the `MOVIE_CSV_B64` Actions secret (see the README "Automatic Deployment" section).
- **Never commit secrets**: Cloudflare tokens, Bing API keys, Telegram bot tokens, Douban cookies, etc. stay out of the repo.
- Poster images are git-ignored (`assets/posters/`).

## Code style

- Keep Python simple, with single-responsibility functions and comments on non-obvious logic.
- `gen_site.py` inlines the core CSS — edit styles there, not in the generated `site/` output.
- Keep changes small and focused; one PR per concern.

## Local toolchain

The `douban_export/` scripts hit the Douban API over the network and need your own cookies / proxy. They store no credentials — configure your own environment.
