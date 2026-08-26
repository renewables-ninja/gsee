# `gsee-climate-data`

Data companion package for [GSEE](https://github.com/renewables-ninja/gsee): monthly probability density functions (PDFs) of daily mean global horizontal irradiance.
These are used by GSEE's climate data interface (`gsee.climate.run_climate` with `pdfs="builtin"`) to synthesize day-to-day variability when running the PV model on annual, seasonal or monthly climate data.

Install together with GSEE via the `climate` extra:

```bash
pip install gsee[climate]
```

## Data provenance

Derived from NASA MERRA-2 reanalysis surface radiation for 2011-2015, aggregated to a 3x3 degree grid over land and near-land cells (latitudes -57 to 72), with per-month histograms of daily irradiance in 128 bins per cell.
This is the same dataset that GSEE v0.3 downloaded at runtime (`MERRA2_rad3x3_2011-2015-PDFs_land_prox.nc`), converted from NetCDF4 to NumPy `.npz` format so that reading it requires nothing beyond numpy.

Arrays in the `.npz` file (see `gsee_climate_data.load()`):

- `xk` — bin values (daily mean irradiance), float32, dims `(lat, lon, month, bins)`
- `pk` — bin probabilities (not normalized), float32, same dims
- `lat`, `lon`, `month` — coordinate vectors (`month` is 1..12)

Cells without data (oceans) hold zeros/NaN probabilities and are treated as "no PDF available" by GSEE.

## Citation

When using this data, please cite MERRA-2:

> Gelaro, R., McCarty, W., Suarez, M. J., et al. (2017). The Modern-Era Retrospective Analysis for Research and Applications, Version 2 (MERRA-2). _Journal of Climate_, 30(14), 5419-5454. <https://doi.org/10.1175/JCLI-D-16-0758.1>

and, for the derived PDFs and the GSEE model that consumes them:

> Pfenninger, S., & Staffell, I. (2016). Long-term patterns of European PV output using 30 years of validated hourly reanalysis and satellite data. _Energy_, 114, 1251-1265. <https://doi.org/10.1016/j.energy.2016.08.060>

## License

Code and data in this package are covered by different terms:

- **Code** — the `gsee_climate_data` Python package is licensed under the BSD 3-Clause License (see `LICENSE`).
- **Data** — the bundled `.npz` is derived from NASA MERRA-2, produced by the NASA Global Modeling and Assimilation Office and distributed by GES DISC.

See `NOTICE` for the full statement.
