# patchkit

Tooling behind the patch-based workflow (`docs/MODUS_OPERANDI.md`).

| File | Purpose |
|---|---|
| `engine.py.tmpl` | The runtime that ships inside every patch script: idempotent operations, in-memory workspace, backups, rollback, CLI. A template, not importable code. |
| `build_patch.py` | Generates `patch_NNNN_<slug>.py` from two trees (pristine vs. changed). |
| `patch_config.example.py` | The configuration the builder expects. |

```bash
# in an AI session: rebuild the owner's tree, copy it, change the copy, then build
python3 tools/unpack_repomix.py repomix-output.xml /tmp/pristine
cp -r /tmp/pristine /tmp/work          # ...edit /tmp/work, run `make check` there...
python3 tools/patchkit/build_patch.py /tmp/pristine /tmp/work patch_0002_example.py \
    --config patch_config.py --handoff handoff_entry.md
```

`tests/test_patchkit.py` builds a patch from two small trees and checks the contract: dry run,
apply, idempotency, anchor drift (no partial writes), merge of `.gitignore`, rollback.
