# EventSpec v5 storage fixture

`mmg_013_storage_extension.json` is a source-only, unaccepted extension of the
exact EventSpec v4 `mmg_013` fixture. Its v4 queue remains an exact prefix. The
v5-only suffix first drops the item that v4 leaves held, then models the closed
transaction sequence:

```text
open fridge -> pick up coffee cup -> insert -> close -> open -> remove
```

`insert` and `remove` compile only to the new canonical
`storage.insert`/`storage.remove` actions. They never resolve to the inherited
generic `insert`, `place`, or `pick_up` semantics. Every document, plan, and
preflight envelope remains `accepted=false` and
`runtime_execution_authorized=false` until dedicated Insert/Remove montages,
typed contact/completion signals, runtime receipts, and visual review exist.
