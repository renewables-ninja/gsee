import math as m
import pandas as pd
import warnings
import numpy as np
import xarray as xr
import scipy.stats as st
from calendar import monthrange
from gsee.climatedata_interface import kt_h_sinusfunc as cyth
from gsee.climatedata_interface.progress import progress_bar
from gsee import trigon, brl_model
from gsee import pv as pv_model


def add_kd_run_gsee(
        df: pd.DataFrame,
        coords: dict,
        frequency: str,
        params: dict) -> pd.Series:
    """
    Calculates diffuse fraction with extraterrestrial radiation and Erb's model and creates
    sinusoidal durinal cycle to create an average day for each month

    Parameters
    ----------
    df : Pandas Dataframe
        containing with single day per month and 'global_horizontal', 'temperature' column


    Returns
    -------
    Pandas Series
        containing column 'pv' with simulated PV power output
    """

    tmp_df = df.copy()
    # Add time of day and eccentricity coefficient
    tmp_df['n'] = tmp_df.index.map(lambda x: x.timetuple().tm_yday)
    tmp_df['Eo'] = tmp_df['n'].map(ecc_corr)

    if frequency == 'H' and 'diffuse_fraction' not in tmp_df.columns:
        # Calculate sunset and sunrise times and write to dataframe:
        if 'rise_set' not in tmp_df:
            daily_df = tmp_df.resample(rule='D').pad()
            daily_df['rise_set'] = trigon.sun_rise_set_times(daily_df.index, coords)
            daily_df = daily_df.reindex(pd.date_range(tmp_df.index[0], tmp_df.index[-1], freq='H'), method='ffill')
            tmp_df['rise_set'] = daily_df['rise_set']
            tmp_df['sunrise_h'] = tmp_df['rise_set'].map(lambda x: decimal_hours(x[0], 'sunrise'))
            tmp_df['sunset_h'] = tmp_df['rise_set'].map(lambda x: decimal_hours(x[1], 'sunset'))
        tmp_df['hour'] = tmp_df.index.hour
        tmp_df_du = tmp_df
    else:
        # Generate durinal cycle for each day:
        tmp_df_du = convert_to_durinal(tmp_df, coords, factor=24)

    # Determine hourly clearness index:
    tmp_df_kd = clearness_index_hourly(tmp_df_du, coords)
    # Calculate diffuse fraction:
    tmp_df_kd['diffuse_fraction'] = brl_model.run(tmp_df_kd['kt_h'], coords, tmp_df_kd['rise_set'].tolist())
    # Run PV-model
    for col in tmp_df_kd.columns:
        if col not in ['global_horizontal', 'diffuse_fraction', 'temperature']:
            tmp_df_kd.drop([col], axis=1, inplace=True)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        pv_h = pv_model.run_model(data=tmp_df_kd, coords=coords, **params)
    if frequency != 'H':
        pv = pv_h.resample(rule='1D').sum()
        pv = pv[pv.index.isin(df.index)]
    else:
        pv = pv_h
    pv = pv[np.isfinite(pv)]
    pv.columns = ['pv']

    return pv


def resample_for_gsee(
        ds: xr.Dataset,
        frequency: str,
        params: dict,
        i: int,
        coords: tuple,
        shr_mem: list,
        prog_mem: list,
        ds_pdfs=None):
    """
    Converts the incoming dataset to dataframe and prepares it
    for GSEE it depending on the temporal resolution.

    Parameters
    ----------
    ds : xarray Dataset
        containing timeseries data of selected coordinates (coords)
    frequency: str
    params : dict
    i : int
    coords : tuple
        coordinates of pv station (lat, lon)
    shr_mem : shared list
        shared memory where all the calculated pv time series are stored
    prog_mem : list
        list indicating the overall progress of the computation, first value ([0]) is the total number
        of coordinate tuples to compute.
    ds_pdfs : xarray Dataset, optional
        Dataset containing xk, pk values for selected coordinates.

    """
    df = ds.to_dataframe()

    if callable(params['tilt']):
        params['tilt'] = params['tilt'](coords[0])

    for col in df.columns:
        if col not in ['global_horizontal', 'diffuse_fraction', 'temperature']:
            df.drop([col], axis=1, inplace=True)

    df = df.replace([np.inf, -np.inf], 0)

    if ds_pdfs is None:
        return _resample_without_pdfs(df, frequency, params, i, coords, shr_mem, prog_mem)
    else:
        return _resample_with_pdfs(df, frequency, params, i, coords, shr_mem, prog_mem, ds_pdfs)


def _resample_without_pdfs(df, frequency, params, i, coords, shr_mem, prog_mem):
    if frequency == 'A':
        # Create 2 days, one in spring and one in autumn, which are then calculated by GSEE
        df.loc[df.index[-1] + pd.DateOffset(years=1)] = np.full(len(df.columns), 0)
        df_yearly12 = df.resample(rule='Q').pad()
        df_yearly12 = df_yearly12[0:-1:2]
        pv = add_kd_run_gsee(df_yearly12, coords, frequency, params)
        pv = pv.resample(rule='A').mean()
    elif frequency in ['S', 'M', 'D']:
        pv = add_kd_run_gsee(df, coords, frequency, params)
    elif frequency == 'H':
        # If diffuse fraction is in df it can be computed directly with the gsee,
        # otherwise 'diffuse_fraction' has to be estimate by BRL-model
        if 'diffuse_fraction' in df.columns:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                pv = pv_model.run_model(
                    data=df, coords=coords, **params)
        else:
            pv = add_kd_run_gsee(df, coords, frequency, params)

    return_pv(pv, shr_mem, prog_mem, coords, i)


def _resample_with_pdfs(df, frequency, params, i, coords, shr_mem, prog_mem, ds_pdfs):
    # Annual and seasonal data are first upsampled to monthly values and then for each month the
    # corresponding number of days is drawn from the PDFs (Probability density functions)
    if frequency == 'S':
        df = df.resample(rule='QS-DEC').bfill()

    df_all = pd.DataFrame()
    # Random days for each month are computed and stitched together to new dataframe:
    for j, row in df.iterrows():
        year = row.name.year
        start_month = row.name.month
        n_months = 1
        if frequency == 'A':
            n_months = 12
        elif frequency == 'S':
            n_months = 3
        rand_days_list = []
        temperatures = []
        monthlist = 2 * list(range(1, 13))
        for mon in monthlist[start_month - 1:start_month + n_months - 1]:
            days = monthrange(year, mon)[1]
            ds_pdfs_mon = ds_pdfs.sel(month=mon)
            rand_days = create_rand_month(xk=ds_pdfs_mon['xk'].values, pk=ds_pdfs_mon['pk'].values,
                                          n=monthrange(year, mon)[1])
            rand_days_list.extend(rand_days)
            if 'temperature' in row:
                temperatures.extend(np.full(days, row['temperature']))
        if any(rand_days_list):
            rand_days_list = [q * (row['global_horizontal'] / np.mean(rand_days_list)) for q in rand_days_list]
        time_index = pd.date_range(start='{}-{}-01'.format(str(year), str(start_month)),
                                   periods=len(rand_days_list), freq='D')
        if 'temperature' in row:
            df_pdf = pd.DataFrame(data={'global_horizontal': rand_days_list, 'temperature': temperatures},
                                  index=time_index)
        else:
            df_pdf = pd.DataFrame(data={'global_horizontal': rand_days_list},
                                  index=time_index)
        df_pdf.index.name = 'time'
        df_all = pd.concat([df_all, df_pdf])

    pv = add_kd_run_gsee(df_all, coords, frequency, params)
    if frequency != 'S':
        pv = pv.resample(rule=frequency).mean()
    elif frequency == 'S':
        pv = pv.resample(rule='QS-DEC').mean()
    return_pv(pv, shr_mem, prog_mem, coords, i)


# ----------------------------------------------------------------------------------------------------------------------
# Support functions
# ----------------------------------------------------------------------------------------------------------------------


def create_rand_month(xk: np.ndarray, pk: np.ndarray, n: int) -> np.ndarray:
        """

        Parameters
        ----------
        xk : List
            of bins of possible radiation values
        pk : List
            Probabilities for the bins in xk to occur
        n : int
            length of the month in days

        Returns
        -------
        List
            of length n with randon values xk following the probabilites given in pk

        """

        multi = 10000  # multiplied as .rvs only gives integer values, but we want a higher resolution
        xk = xk * multi

        if sum(pk) and sum(pk) > 0:
            pk = pk / sum(pk)  # normalized so sum(pk)==1
            try:
                custm = st.rv_discrete(name='custm', values=(xk, pk))
            except Exception:
                raise ValueError('Sum provided pk is not 1')
            r = custm.rvs(size=n) / multi
            return r
        else:
            return np.full(n, 0)


def clearness_index_hourly(df: pd.DataFrame, coords: tuple) -> pd.DataFrame:
    """
    Calculates hourly clearness index and also adds sunrise and sunset to the dataframe
    as separate columns if not yet present. Following Equations from Elminir2007 (Prediction of hourly and daily
    diffuse fraction using neural network, as compared to linear regression models)

    Parameters
    ----------
    df : Pandas Dataframe
        containing columns: 'n', 'hour', 'Eo', 'sunrise_h', 'global_horizontal'
    coords : Tuple
        coordinates of pv station (lat, lon)

    Returns
    -------
    Pandas Dataframe:
        Same as df but with additional column "kt_h" = hourly clearness index
    """
    lat = m.radians(coords[0])
    S = 1367  # Solar constant in W/m2
    df['kt_h'] = cyth.apply_kt_h(S, lat, df['n'].values, df['hour'].values,
                                 df['Eo'].values, df['sunrise_h'].values,
                                 df['global_horizontal'].values)

    return df


def convert_to_durinal(data: pd.DataFrame, coords: tuple, factor=1) -> pd.DataFrame:
    """

    Parameters
    ----------
    data : Pandas dataframe
        with datetimeindex and column 'global_horizontal'
    coords : Tuple
        coordinates of pv station (lat, lon)
    factor : int
        by which the incoming data is multiplied, used to convert W to Wh/day
    Returns
    -------
    Pandas dataframe
        with hourly values and column 'global horizontal' following a sinusoidal function
    """

    def _upsample_df_single_day(indf):
        """Upsamples dataframe to hourly values but only fills the days that were in the original dataframe
        and drops all other rows
        """
        df = indf.copy()
        # add line at the end so resample treats it like a whole day:
        df.loc[df.index[-1] + pd.Timedelta('1D')] = np.full(len(df.columns), 0)
        df = df.resample(rule='1H').pad(limit=23)
        # removing last line again:
        df = df.drop(df.index[-1])
        return df.dropna(how='all')

    # Calculate sunset and sunrise times and write to dataframe:
    if 'rise_set' not in data:
        data['rise_set'] = trigon.sun_rise_set_times(data.index, coords)
        data['sunrise_h'] = data['rise_set'].map(lambda x: decimal_hours(x[0], 'sunrise'))
        data['sunset_h'] = data['rise_set'].map(lambda x: decimal_hours(x[1], 'sunset'))
    # Upsample the data to hourly timestamps and calculate the hourly irradiance:
    data.loc[:, 'global_horizontal_day'] = factor * data['global_horizontal'].copy()
    daily = _upsample_df_single_day(data)
    daily['hour'] = daily.index.hour
    daily['global_horizontal'] = cyth.apply_csinus_func(daily['sunrise_h'].values,
                                                        daily['sunset_h'].values,
                                                        daily['hour'].values,
                                                        daily['global_horizontal_day'].values)
    mean_daily = daily['global_horizontal'].resample(rule='D').mean()
    corr_fact = mean_daily / data['global_horizontal']
    ups_corr_fact = _upsample_df_single_day(corr_fact.to_frame())
    daily_corr = daily['global_horizontal'] / ups_corr_fact['global_horizontal']
    daily['global_horizontal'] = daily_corr

    return daily


def ecc_corr(n: int) -> float:
    """
    Parameters
    ----------
    n: int
        day of the year

    Returns
    -------
    float
        Eccentricity coefficient
    """

    t = (2 * m.pi * (n - 1)) / 365
    Eo = (1.000110 + 0.034221 * m.cos(t) +
          0.001280 * m.sin(t) +
          0.000719 * m.cos(2 * t) +
          0.00077 * m.sin(2 * t))
    return Eo


def decimal_hours(timeobject, rise_or_set: str) -> float:
    """
    Parameters
    ----------
    timeobject : datetime object
        Sunrise or -set time
    rise_or_set: string
        'sunrise' or 'sunset' specifiying which of the two timeobject is
    Returns
    -------
    float
        time of timeobject in decimal hours

    """
    assert rise_or_set == 'sunrise' or rise_or_set == 'sunset'

    if timeobject:
        ret = timeobject.hour + timeobject.minute / 60
        if ret == 0:
            return 0.0
        else:
            return ret
    elif rise_or_set == 'sunrise':
        return 0.0
    elif rise_or_set == 'sunset':
        return 23.999


def return_pv(pv: pd.Series, shr_mem: list, prog_mem: list, coords: tuple, i: int):
    """
    Does necessary stuff to pv to convert it back to xarray (adds lat, lon) and saves it to shr_mem
    also updates and draws progress bar

    Parameters
    ----------
    pv : Pandas series
        containing calculated pv values
    shr_mem : List
        shared memory where all the calculated pv time series are stored
    prog_mem : List
        list indicating the overall progress of the computation, first value ([0]) is the total number
    of coordinate tuples to compute.
    coords : Tuple
        coordinates of pv station (lat, lon)
    i : int
        index where in shr_mem to save pv, unique for every coordinate tuple
    """

    pv = pv.to_frame()
    pv.columns = ['pv']
    pv.reset_index(inplace=True)
    pv['lat'] = coords[0]
    pv['lon'] = coords[1]
    pv.set_index(['lon', 'lat', 'time'], inplace=True)
    shr_mem[i] = pv.to_xarray()
    prog_mem.append(1)
    len_coord_list = prog_mem[0]
    progress_bar(len(prog_mem), len_coord_list)
