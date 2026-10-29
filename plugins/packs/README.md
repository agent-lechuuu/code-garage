# Trusted skill packs

Each folder here is one plugin made of third-party Agent Skills that are **trusted** (trust/registry.yaml: reviewed,
scanned and approved by the owner at the pinned sha) and **permissively licensed**. Nothing else goes in.

```
plugins/packs/<pack>/
  .claude-plugin/plugin.json      name "<pack>", description, license of the pack glue (MIT)
  skills/<skill>/SKILL.md         copied unmodified from upstream at the pinned sha
  skills/<skill>/LICENSE          the upstream licence (and NOTICE when there is one)
  skills/<skill>/.garage.json     upstream url, sha, licence, date (written by `garage skill add`)
```

A pack is listed in `.claude-plugin/marketplace.json` as `{"name": "<pack>", "source": "./plugins/packs/<pack>"}`
only after `claude plugin validate .` passes. A pin bump drops the item to `reviewed`; the pack copy is then removed
until it is trusted again (CI enforces this through `garage validate`).
