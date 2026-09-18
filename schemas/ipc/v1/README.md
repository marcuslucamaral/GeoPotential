# IPC schemas, version 1.0.0

Generated from `worker/geopotential_worker/protocol.py` by
`tools/generate_ipc_schemas.py`. `REQUIRED` in that module is the
single source; do not hand-edit these files.

| Message | Direction |
|---|---|
| `cancel_job` | app -> worker |
| `goodbye` | worker -> app |
| `hello` | worker -> app |
| `job_artifact` | worker -> app |
| `job_failed` | worker -> app |
| `job_progress` | worker -> app |
| `job_succeeded` | worker -> app |
| `shutdown` | app -> worker |
| `submit_job` | app -> worker |

Changing any of them obliges the seven steps of
`IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` section 29: alter the schema,
version it, update the producer, update the consumer, update the
compatibility test, update the documentation, and update the golden
output where one exists.
