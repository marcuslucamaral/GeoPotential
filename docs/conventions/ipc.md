# Protocol and schema rules

The protocol is the only thing that crosses the process boundary. It is the
one contract that, if it drifts, makes both halves individually correct and
jointly broken.

## One file, two places

`worker/geopotential_worker/protocol.py` and
`app/geopotential_app/ipc/protocol.py` are **byte-identical**.

The app may not import the worker package — that would reintroduce the coupling
process separation exists to remove — and a hand-maintained second copy drifts.
So the copy is mechanical and the sameness is gated twice: by
`architecture_check.py` (`protocol-mirrors`) and by `tests/contract/`.

**To change the protocol:** edit the worker's copy, `cp` it over the app's,
regenerate the schemas, run the gate.

## Transport

- **JSON Lines. One message per line. UTF-8.** A newline inside a message
  desynchronizes the stream, so `encode` uses compact separators and the
  contract suite asserts a message contains no newline.
- **No HTTP, no localhost, no port.** `--self-test` asserts the process has no
  listening TCP socket and has imported no web module.
- **Never serialize a raster.** Large data travels as a file — GeoTIFF, COG,
  GeoPackage — and the message carries a path, a type and a hash.
- **stdout is the protocol; stderr is the log.** Separate channels, always.

## The envelope

`message()` writes `type` and `protocol` **last**, so a body field can never
shadow the message kind. This is not defensive clutter: the first
`job_artifact` this project emitted went out as `{"type":"GeoTIFF",...}`
because §12.3 names the artefact's format field `type` and the envelope already
owned that key. The artefact's field is `artifact_type`, and the deviation is
recorded in the generated schema.

## Validation

- Every message declares its required fields in `REQUIRED`, and both `message()`
  and `decode()` check them. A missing field is a `ProtocolError`, never a
  default.
- **A major-version mismatch blocks execution.** It never degrades into a
  partial mode where some operators happen to work. `compatible()` compares
  MAJOR only.
- An unreadable line is reported and skipped with a `job_failed`; it never
  crashes the loop.

## The job state machine

`Succeeded` is reachable **only** from `Committing`, and `Committing` cannot be
cancelled. Those two facts together are why a partial output can never be
published as a result. Both are asserted, by name, in `tests/contract/`.

Do not add a transition without asking what partial state it would let escape.

## Progress

`fraction` is **derived from work actually done** and is monotonic within a
stage. Progress advanced on a timer is a defect. The model drops a fraction
that goes backwards within a stage rather than displaying it.

## Errors

`job_failed` carries `safe_message` for the user and `detail_ref` for the log.
The traceback does not reach the user by default. A safe message answers, where
it can: what failed, why, which dataset, which parameter, what to correct, and
where the technical detail is.

## Schemas

`schemas/ipc/v1/` is **generated** from `protocol.REQUIRED` by
`tools/generate_ipc_schemas.py`. Do not hand-edit those files; the gate
regenerates and compares, so a protocol change that forgot to regenerate is
caught rather than trusted.

## Changing anything

Section 29, all seven steps, no exceptions:

1. alter the schema;
2. version the schema;
3. update the producer;
4. update the consumer;
5. update the compatibility test;
6. update the documentation;
7. update the golden output where one exists.

**Never change a contract silently.**
