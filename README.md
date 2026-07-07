[![Tests](https://img.shields.io/github/actions/workflow/status/renewables-ninja/gsee/test.yml?style=flat-square&label=tests)](https://github.com/renewables-ninja/gsee/actions/workflows/test.yml)
[![Test coverage](https://img.shields.io/codecov/c/github/renewables-ninja/gsee?style=flat-square)](https://codecov.io/gh/renewables-ninja/gsee)
[![PyPI version](https://img.shields.io/pypi/v/gsee.svg?style=flat-square)](https://pypi.python.org/pypi/gsee)
[![conda-forge version](https://img.shields.io/conda/vn/conda-forge/gsee.svg?style=flat-square)](https://anaconda.org/conda-forge/gsee)

# GSEE: Global Solar Energy Estimator

`GSEE` is a solar energy simulation library designed for rapid calculations and ease of use. It can run for a single site with a pandas DataFrame to hundreds of thousands of sites or global grids with xarray Datasets. [Renewables.ninja](https://www.renewables.ninja/) uses `GSEE`.

The development of `GSEE` predates the existence of [`pvlib-python`](https://pvlib-python.readthedocs.io/) but builds on its functionality as of v0.4.0. Use `GSEE` if you want fast simulations with sensible defaults and/or its climate data interface, and `pvlib-python` if you need control over the nuts and bolts of simulating PV systems.

## Installation

    pip install gsee

To also install the built-in irradiance probability density functions used by the climate data interface:

    pip install gsee[climate]

`GSEE` is also available via `conda-forge`.

## Documentation

See the [documentation](https://gsee.readthedocs.io/) for more information on `GSEE`'s functionality and for examples.

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
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification. Contributions of any kind welcome!