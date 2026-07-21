<h1 style="font-size: 2.1rem; margin: 0">GSEE: Global Solar Energy Estimator</h1>

---

[![Tests](https://img.shields.io/github/actions/workflow/status/renewables-ninja/gsee/test.yml?style=flat-square&label=tests)](https://github.com/renewables-ninja/gsee/actions/workflows/test.yml)
[![Test coverage](https://img.shields.io/codecov/c/github/renewables-ninja/gsee?style=flat-square)](https://codecov.io/gh/renewables-ninja/gsee)
[![PyPI version](https://img.shields.io/pypi/v/gsee.svg?style=flat-square)](https://pypi.python.org/pypi/gsee)
[![conda-forge version](https://img.shields.io/conda/vn/conda-forge/gsee.svg?style=flat-square)](https://anaconda.org/conda-forge/gsee)

<br>

`GSEE` is a solar energy simulation library designed for rapid calculations and ease of use, from a single site with a pandas DataFrame to hundreds of thousands of sites or global grids with xarray Datasets. [Renewables.ninja](https://www.renewables.ninja/) uses `GSEE`.

The development of `GSEE` predates the existence of [`pvlib-python`](https://pvlib-python.readthedocs.io/) but builds on its functionality as of v0.4.0. Use `GSEE` if you want fast simulations with sensible defaults, and `pvlib-python` if you need control over the nuts and bolts of simulating PV systems.

Upgrading from an older version? See the [guide on migrating from v0.3 to v0.4](migrating.md).

## Installation

    pip install gsee

To also install the built-in irradiance probability density functions used by the [climate data interface](climatedata-interface.md) (the `gsee-climate-data` companion package):

    pip install gsee[climate]

`GSEE` is also available via `conda-forge` (`conda install -c conda-forge gsee`); the `gsee-climate-data` companion package must currently be installed with `pip`.

See [Development](development.md) for installing a development build.

## Functionality

There are three entry points, from single sites to global grids:

- **Single site**: [`gsee.pv.run_model()`](running/index.md) simulates one PV system from a pandas DataFrame of hourly or finer irradiance data.
- **Many sites or grids**: [`gsee.api.run_sites()` and `gsee.api.run_grid()`](running/multi-site.md) simulate many sites at once on a vectorized computation core, at roughly 20x lower per-site cost than the single-site path, with chunked and optionally parallel execution.
- **Climate data**: [`gsee.climate.run_climate()`](climatedata-interface.md) runs the PV model directly on gridded climate data at annual, seasonal, monthly, daily or hourly resolution, synthesizing hourly irradiance where needed.

Underneath sit the lower-level modules:

- **`gsee.core`**: the vectorized multi-site computation core (solar position, plane-of-array irradiance, panel and inverter models, [diffuse-fraction estimation](diffuse-fraction.md), hourly synthesis) operating on `(time, site)` numpy arrays.
- **`gsee.legacy`**: the frozen pre-0.4 single-site implementation (ephem-based solar positions and the original BRL diffuse-fraction model), kept only to replicate older simulation runs; requires the optional `legacy` extra (`pip install gsee[legacy]`), see [Legacy options](running/legacy.md).

## Examples

### Power output from a PV system with fixed panels

`data` must be a pandas.DataFrame with columns `global_horizontal` (in W/m2), `diffuse_fraction`, and optionally a `temperature` column for ambient air temperature (in degrees Celsius), indexed with a timezone-aware UTC DatetimeIndex.

```python
result = gsee.pv.run_model(
    data,
    coords=(22.78, 5.51),  # Latitude and longitude
    tilt=30,  # 30 degrees tilt angle
    azim=180,  # facing towards equator,
    tracking=0,  # fixed - no tracking
    capacity=1000,  # 1000 W
)
```

### Power output from many sites at once

```python
result = gsee.api.run_sites(
    dataset,  # xarray.Dataset over (time, site), see the multi-site documentation
    tilt=30,
    azim=180,
    tracking=0,
    capacity=1000,
)
```

See [Multi-site simulations](running/multi-site.md) for the input format and the scaling options (chunking, worker processes, float32 mode, streaming input data from disk).

### In-plane irradiance and other intermediate results

`include_raw_data=True` returns a DataFrame that includes the in-plane direct and diffuse irradiance, module temperature and relative efficiency alongside the power output:

```python
result = gsee.pv.run_model(
    data,
    coords=(22.78, 5.51),
    tilt=30,
    azim=180,
    tracking=2,  # 2-axis tracking
    capacity=1000,
    include_raw_data=True,
)
plane_irradiance = result[["direct", "diffuse"]]
```

### PV output from gridded monthly climate data

```python
result = gsee.climate.run_climate(
    dataset,  # xarray.Dataset over (time, lat, lon) with monthly mean irradiance
    tilt=35,
    azim=180,
    tracking=0,
    capacity=1000,
    pdfs="builtin",  # requires `pip install gsee[climate]`
)
```

See the [climate data interface documentation](climatedata-interface.md) for details.

## Credits and contact

Contact [Stefan Pfenninger](mailto:s.pfenninger@tudelft.nl) for questions about `GSEE`. `GSEE` is also a component of the [Renewables.ninja](https://www.renewables.ninja) project, developed by Stefan Pfenninger and Iain Staffell. Use the [contact page](https://www.renewables.ninja/about) there if you want more information about Renewables.ninja.

## Citation

If you use `GSEE` or code derived from it in academic work, please cite:

Stefan Pfenninger and Iain Staffell (2016). Long-term patterns of European PV output using 30 years of validated hourly reanalysis and satellite data. _Energy_ 114, pp. 1251-1265. [doi: 10.1016/j.energy.2016.08.060](https://doi.org/10.1016/j.energy.2016.08.060)

## License

BSD-3-Clause

## Contributors ✨

Thanks goes to these wonderful people ([emoji key](https://allcontributors.org/docs/en/emoji-key)):

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/sjpfenninger"><img src="https://avatars.githubusercontent.com/u/141709?v=4?s=100" width="100px;" alt="Stefan Pfenninger-Lee"/><br /><sub><b>Stefan Pfenninger-Lee</b></sub></a><br /><a href="https://github.com/renewables-ninja/gsee/commits?author=sjpfenninger" title="Code">💻</a> <a href="#ideas-sjpfenninger" title="Ideas, Planning, & Feedback">🤔</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/iain-staffell"><img src="https://avatars.githubusercontent.com/u/30894186?v=4?s=100" width="100px;" alt="Iain Staffell"/><br /><sub><b>Iain Staffell</b></sub></a><br /><a href="#ideas-iain-staffell" title="Ideas, Planning, & Feedback">🤔</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/muelljoh"><img src="https://avatars.githubusercontent.com/u/42338028?v=4?s=100" width="100px;" alt="Johannes"/><br /><sub><b>Johannes</b></sub></a><br /><a href="https://github.com/renewables-ninja/gsee/commits?author=muelljoh" title="Code">💻</a> <a href="#ideas-muelljoh" title="Ideas, Planning, & Feedback">🤔</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://www.tsaoyu.com/"><img src="https://avatars.githubusercontent.com/u/6488896?v=4?s=100" width="100px;" alt="Tony Yu Cao"/><br /><sub><b>Tony Yu Cao</b></sub></a><br /><a href="https://github.com/renewables-ninja/gsee/issues?q=author%3Atsaoyu" title="Bug reports">🐛</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/jwohland"><img src="https://avatars.githubusercontent.com/u/20681098?v=4?s=100" width="100px;" alt="Jan Wohland"/><br /><sub><b>Jan Wohland</b></sub></a><br /><a href="https://github.com/renewables-ninja/gsee/issues?q=author%3Ajwohland" title="Bug reports">🐛</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/LinhHo"><img src="https://avatars.githubusercontent.com/u/45103089?v=4?s=100" width="100px;" alt="Linh Ho"/><br /><sub><b>Linh Ho</b></sub></a><br /><a href="https://github.com/renewables-ninja/gsee/commits?author=LinhHo" title="Code">💻</a> <a href="#ideas-LinhHo" title="Ideas, Planning, & Feedback">🤔</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/MaykThewessen"><img src="https://avatars.githubusercontent.com/u/18009395?v=4?s=100" width="100px;" alt="Mayk Thewessen"/><br /><sub><b>Mayk Thewessen</b></sub></a><br /><a href="https://github.com/renewables-ninja/gsee/commits?author=MaykThewessen" title="Code">💻</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification. Contributions of any kind welcome!
