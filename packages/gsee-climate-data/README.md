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
