# Legacy options

GSEE v0.4.0 replaces several internals with improved implementations, moving the pre-0.4 code into `gsee.legacy`.

`gsee.legacy` requires the `ephem` library, which is no longer a required dependency of GSEE. Install it via the optional `legacy` extra:

```shell
pip install gsee[legacy]
```

- `gsee.legacy.run_model(...)` reproduces runs made with the pre-0.4 pvlib-based solar positions.
- `gsee.legacy.run_model(..., legacy_solarposition=True)` reproduces runs using the ephem-based solar position calculation with its hour-based sunshine-duration model of sunrise and sunset timesteps.

The underlying solar geometry functions remain available in `gsee.legacy.trigon` (e.g. `sun_angles()`, `sun_angles_legacy()`, `aperture_irradiance()`).

The original single-site, ephem-based BRL diffuse-fraction implementation is kept unchanged as a frozen reference in `gsee.legacy.brl_model`.

## What the legacy path does not support

`gsee.legacy` is frozen at its pre-0.4 behaviour, so options introduced in 0.4 are
rejected with an explicit error rather than silently ignored. Passing any of these
together with `legacy_solarposition=True` raises `ValueError`:

- `temperature_correction_method` -- the frozen panels never cap relative efficiency.
- `albedo` other than the default `0.3` -- the frozen code always uses `0.3`.
- `technology` other than `'csi'`, `'cis'` or `'cdte'` -- the newer `'csi-new'`,
  `'cec-csi-median'` and `'singlediode'` models postdate it.

!!! warning "Deprecated aliases"
    Passing `legacy_solarposition=True` to `gsee.pv.run_model()` still works and delegates to `gsee.legacy.run_model()`, but is deprecated and will be removed in 0.5.0. The module aliases `gsee.trigon` and `gsee.brl_model` (pointing at their `gsee.legacy` counterparts) are likewise deprecated and will be removed in 0.5.0.
