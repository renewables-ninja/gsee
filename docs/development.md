# Development

## Environment

Development uses [pixi](https://pixi.sh/) to manage the environment:

```bash
git clone https://github.com/renewables-ninja/gsee
cd gsee
pixi install
```

Available tasks:

| Task                               | Purpose                                    |
| ---------------------------------- | ------------------------------------------ |
| `pixi run test`                    | run the test suite                         |
| `pixi run test -m "not reference"` | skip the slower reference regression tests |
| `pixi run format`                  | format code with ruff                      |
| `pixi run lint`                    | lint with ruff                             |
| `pixi run generate-reference`      | regenerate the reference data (see below)  |
| `pixi run benchmark`               | run the performance benchmarks             |
| `pixi run docs-serve`              | serve this documentation locally           |

## Repository layout

```
src/gsee/            the gsee package
  core/              vectorized (time, site) computation core
  api.py             multi-site entry points (run_sites, run_grid)
  climate.py         climate data interface
  pv.py              single-site entry point (run_model) and panel models
  legacy/            legacy pre-0.4 pipeline
packages/
  gsee-climate-data/ optional data companion package (built-in PDFs for climate.py)
tests/
  reference/         reference regression framework and committed data
benchmarks/          performance benchmark runner
```

## Releases

Record user-facing changes in `CHANGELOG.md` under the current development version heading.

The `gsee-climate-data` companion package under `packages/` is versioned and released separately (it should change only when the bundled data changes).

Publishing to PyPI is automated through GitHub (`.github/workflows/release.yml`).

- Pushing a tag `vX.Y.Z` builds and publishes `gsee`.
- Pushing `climate-data-vX.Y.Z` builds and publishes the `gsee-climate-data` companion package from `packages/`.

Both jobs verify that the tag matches the package version before building.

## Reference regression tests

`tests/reference/` contains committed reference data: model inputs (deterministic synthetic weather from `gsee.synthetic`) and outputs for 45 cases covering a nine-site range of latitudes, including polar day/night at Svalbard and in Antarctica, with different variants for tracking, technology, inverter and resolution.

`tests/test_reference.py` recomputes every case and compares against the stored data using two tolerance profiles (defined in `tests/reference/compare.py`):

- **"exact"** ensures that the implementation does not drift by enforcing limits just above the quantization of the stored data.
- **"physical"** is a realistic bar for new implementations, representing physical equivalence within tolerances (e.g. 0.5% annual energy, 1%-of-capacity hourly RMSE).

If reference tests fail and the failure report says the physical profile still passes, results shifted within tolerance.
This could be caused e.g. by a dependency upgrade.
If the change is physically plausible, the reference data can be re-generated with `pixi run generate-reference` and committed together with what caused the change.

## Benchmarks

`pixi run benchmark` times the pipeline stages and end-to-end runs, prints a table, and stores JSON results under `benchmarks/results/`.
To compare two runs, e.g. across branches:

```bash
pixi run benchmark --compare benchmarks/results/<baseline>.json
```

A GitHub workflow (`.github/workflows/benchmark.yml`) runs the benchmarks monthly and on demand, uploading the JSON results as artifacts.
