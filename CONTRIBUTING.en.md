# Contributing

Improvements, ideas and bug reports are welcome, in German or English. Jarvis is a private hobby project; replies may
take a few days.

## How

- **Bug or idea:** open an issue. For bugs, please include what you did, what happened and what you expected,
  plus the version (PC client, app, setup) and the relevant excerpt from the log. **Don't paste tokens, keys, addresses
  or conversation content** into it.
- **Security vulnerability:** not as an issue, but as described in [SECURITY.en.md](SECURITY.en.md).
- **Code:** a pull request with one change per topic. Briefly describe what and why, and how you tested it.
  The unit tests under `vorlagen/bruecke/` must pass.

## Rules for contributions

- Nothing personal in code, examples or images: no real names, addresses, identifiers or screenshots
  with private data.
- New features don't change existing behavior on their own. A new switch starts out at the state
  that existed before.
- Tools with an effect on the outside world (messages, devices, purchases) need an approval and a test mode.

## License of your contributions

Jarvis is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE): free for personal and other
noncommercial purposes, commercial use only with permission.

By opening a pull request you declare:

1. The contribution is yours, or you are allowed to submit it.
2. You license it under the same license as the project.
3. The project owner may additionally pass on your contribution under other terms, for example for a permitted
   commercial use or a later license change. Without this point, every such change would need the
   consent of everyone who has ever contributed.
