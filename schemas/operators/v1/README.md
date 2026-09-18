# Operator contracts, version 1

Generated from `worker/geopotential_worker/operators/registry.py` by
`tools/export_project_schema.py`. Do not hand-edit.

`registered.json` is what the worker announces in `hello.capabilities`
and is therefore what the application may offer. Each entry carries its
parameters with type, unit, documented default and range, plus the
literature reference. Section 16: no default is silent.

`planned.json` is what the milestones will add. The interface shows
these disabled and names the milestone, rather than offering an
operation that fails after the click.

## Registered (27)

- `decision.aggregate`
- `decision.ahp_weights`
- `decision.membership`
- `grid.compare_policies`
- `grid.cross_validate`
- `grid.difference`
- `grid.euclidean_distance`
- `grid.harmonize`
- `grid.idw`
- `grid.rasterize`
- `grid.tin_cubic`
- `grid.tin_linear`
- `io.describe_dataset`
- `potential_fields.analytic_signal`
- `potential_fields.derivative`
- `potential_fields.radial_spectrum`
- `potential_fields.regional_residual`
- `potential_fields.rtp`
- `potential_fields.tilt`
- `potential_fields.total_horizontal_gradient`
- `potential_fields.upward_continuation`
- `qc.validate_dataset`
- `reporting.manifest`
- `scenarios.explain`
- `scenarios.leave_one_out`
- `scenarios.rank_targets`
- `scenarios.sensitivity`

## Planned (1)

| Operator | Milestone |
|---|---|
| `reporting.report` | M8 |
