import math as m
import pandas as pd
import warnings
import numpy as np
import sys
import scipy.stats as st
from calendar import monthrange
from gsee.climdata_interface import cyth_func as cyth
from gsee import trigon, brl_model
from gsee import pv as pv_model

def decimal_hours(timeobject, rise_or_set):
    """
    :param timeobject: Sunrise or -set time
    :param rise_or_set: string 'sunrise' or 'sunset' specifiying what timeobject is
    :return: time of timeobject in decimal hours
    """
    if timeobject:
        ret =  timeobject.hour + timeobject.minute / 60
        if ret == 0:
            return 0.0
        else:
            return ret
    elif rise_or_set == 'sunrise':
        return 0.0
    elif rise_or_set == 'sunset':
        return 23.999


def create_rand_month(xk, pk, n):
    """
    :param xk: array of bins of possible radiation values
    :param pk: possiblities for the bins in xk to occur
    :param n: length of month
    :return: array of length n with randon values xk following the probabilites given in pk
    """
    multi = 10000 # multiplied as .rvs only gives integer values, but we want a higher resolution
    xk = xk * multi

    if sum(pk) and sum(pk) > 0:
        pk = pk / sum(pk) # normalized so sum(pk)==1
        try:
            custm = st.rv_discrete(name='custm',values=(xk,pk))
        except:
            raise ValueError('Sum provided pk is not 1')
        r = custm.rvs(size=n)/multi
        return r
    else:
        return np.full(n, 0)


def convert_to_durinal(data, coords, factor=1):
    """
    Upsamples data to hourly values by applying a sinusoidal function to the column 'global_horizontal',
     simulating a diurnal cycle
    :param data: Dataframe with datetimeindex and column 'global_horizontal'
    :param coords: coordinates of PV panel
    :param factor: by which the incoming data is multiplied, used to convert W to Wh/day
    :return: Dataframe with hourly values and column 'global horizontal' following a sinusoidal function
    """
    def _upsample_df_single_day(indf):
        """
        Upsamples dataframe to hourly values but only fills the days that were in the original dataframe
        and drops all other rows
        """
        df = indf.copy()
        # add line at the end so resample treats it like a whole day:
        df.ix[df.index[-1] + pd.Timedelta('1D')] = np.full(len(df.columns), 0)
        df = df.resample(rule='1H').pad(limit=23)
        # removing last line again:
        df = df.drop(df.index[-1])
        return df.dropna(how='all')


    # Calculate sunset and sunrise times and write to dataframe:
    if not 'rise_set' in data:
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
    return daily


def clearness_index_hourly_cython(df, coords):
    '''
    Calculates hourly clearness index and also adds sunrise and sunset to the dataframe
    as separate columns if not yet present. Following Equations from Elminir2007 (Prediction of hourly and daily
    diffuse fraction using neural network, as compared to linear regression models)
    :param df: dataframe with columns: 'n', 'hour', 'Eo', 'sunrise_h', 'global_horizontal'
    :param coordinates of location: tuple(lat, lon)
    :return: dataframe with new column "kt_h" = hourly clearness index
    '''

    lat = m.radians(coords[0])
    S = 1.367  # Solar constant in kW/m2
    df['kt_h'] = cyth.apply_extraterr(S, lat, df['n'].values, df['hour'].values,
                                      df['Eo'].values, df['sunrise_h'].values,
                                      df['global_horizontal'].values)

    return df


def kd_and_gsee(df, station):
    """
    Calculates diffuse fraction with extraterrestrial radiation and Erb's model and creates
    sinusoidal durinal cycle to create an average day for each month
    :param df: dataframe with single day per month and global_horizontal, temperature column
    :param coords: tuple with (latitude,longitude)
    :param station: object of type PVstation with tilt, azim, tracking, capacity attributes
    :return:two np-arrays with pv-power and diffuse fraction in advancing time
    """

    def _ecc_corr(n):
        '''
        :param n: day of the year
        :return: Eccentricity coefficient
        '''
        t = (2 * m.pi * (n - 1)) / 365
        Eo = (1.000110 + 0.034221 * m.cos(t) + 0.001280 * m.sin(t) + 0.000719 * m.cos(2 * t) + 0.00077 * m.sin(2 * t))
        return Eo

    coords = station.coords

    tmp_df = df.copy()
    tmp_df['n'] = tmp_df.index.map(lambda x: x.timetuple().tm_yday)
    tmp_df['Eo'] = tmp_df['n'].map(_ecc_corr)

    if station.data_freq == 'H' and 'diffuse_fraction' not in tmp_df.columns:
        # Calculate sunset and sunrise times and write to dataframe:
        if not 'rise_set' in tmp_df:
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
    tmp_df_kd = clearness_index_hourly_cython(tmp_df_du, coords)

    # Calculate diffuse fraction:
    tmp_df_kd['diffuse_fraction'] = brl_model.run(tmp_df_kd['kt_h'], coords, tmp_df_kd['rise_set'].tolist())
    # Run PV-model
    for col in tmp_df_kd.columns:
        if col not in ['global_horizontal', 'diffuse_fraction', 'temperature']:
            tmp_df_kd.drop([col], axis=1, inplace=True)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        pv_h = pv_model.run_model(data=tmp_df_kd, coords=coords, tilt=station.tilt, azim=station.azim,
                              tracking=station.tracking, capacity=station.capacity)

    if station.data_freq != 'H':
        pv = pv_h.resample(rule='1D').sum()
    else:
        pv = pv_h
    pv = pv[np.isfinite(pv)]
    pv.columns = ['pv']

    return pv


def progress_bar(current_length, total):
    """
    Draws a progress bar in the terminal depending on:
    :param current_length: Is the length of the shared memory list "prog_mem",
     representing the number of processed coordinate tuples
    :param total: is the total amount oc coordinate tuples to process
    """
    curr = current_length - 1
    width = 75
    fract = curr / total
    progress = int(fract * width)
    left = width - progress
    sys.stdout.write('\r\t[{}{}{}] {}%'.format((progress-2)*'=', 2*'>', left*' ',  round(fract*100)))
    sys.stdout.flush()


def process_return_pv(pv, shr_mem, prog_mem, coords, i):
    """
    Does necessary stuff to pv to convert it back to xarray (adds lat, lon) and saves it to shr_mem
    also updates and draws progress bar
    :param pv: pandas series with pv values calculated
    :param shr_mem: shared memory where all the calculated pv time series are stored
    :param prog_mem: list indicating the overall progress of the computation, first value ([0]) is the total number
    of coordinate tuples to compute.
    :param coords: coordinates of pv station
    :param i: index where in shr_mem to save pv
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


def run_gsee(ds, instation, i, coords, shr_mem, prog_mem):
    """
    Converts the incoming dataset to dataframe and pre-processes it depending on the temporal resolution
    :param ds: xarray dataset with selected coordinates of coords, is now similar to a timeseries
    :param instation: PVstation object where tilt has not been set yet, but all other atributes are
    :param i: index where in shr_mem to save pv
    :param coords: coordinates of pv station
    :param shr_mem: shared memory where all the calculated pv time series are stored
    :param prog_mem: list indicating the overall progress of the computation, first value ([0]) is the total number
    of coordinate tuples to compute.
    """
    df = ds.to_dataframe()
    station = PVstation(instation.tilt(coords[0]), instation.azim, instation.tracking,
                        instation.capacity, instation.data_freq)
    station.coords = coords
    # Store data_freq in station object:
    data_freq = station.data_freq

    df = df.drop(['lon', 'lat'], axis=1)
    for col in df.columns:
        if col not in ['global_horizontal', 'diffuse_fraction', 'temperature']:
            df.drop([col], axis=1, inplace=True)
    df = df.replace([np.inf, -np.inf], 0)

    if data_freq == 'A':
        # Create 2 days, one in spring and one in autumn, which are then calculated by GSEE
        df.ix[df.index[-1] + pd.Timedelta('365D')] = np.full(len(df.columns), 0)
        df_yearly12 = df.resample(rule='Q').pad()
        df_yearly12 = df_yearly12[0:-1:2]
        pv = kd_and_gsee(df=df_yearly12, station=station)
        pv = pv.resample(rule='A').mean()
    elif data_freq in ['S', 'M', 'D']:
        pv = kd_and_gsee(df=df, station=station)
    elif data_freq == 'H':
        # If diffuse fraction is in df it can be computed directly with the gsee,
        # otherwise 'diffuse_fraction' has to be estimate by BRL-model
        if 'diffuse_fraction' in df.columns:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                pv = pv_model.run_model(data=df, coords=coords, tilt=station.tilt, azim=station.azim,
                                    tracking=station.tracking, capacity=station.capacity)
        else:
            pv = kd_and_gsee(df=df, station=station)
    process_return_pv(pv, shr_mem, prog_mem, coords, i)


def run_gsee_pdfs(ds, instation, i, coords, shr_mem, prog_mem, ds_pdfs):
    """
    Converts the incoming dataset to dataframe and pre-processes it depending on the temporal resolution
    :param ds: xarray dataset with selected coordinates of coords, is now similar to a timeseries
    :param instation: PVstation object where tilt has not been set yet, but all other atributes are
    :param i: index where in shr_mem to save pv
    :param coords: coordinates of pv station
    :param shr_mem: shared memory where all the calculated pv time series are stored
    :param prog_mem: list indicating the overall progress of the computation, first value ([0]) is the total number
    of coordinate tuples to compute.
    :param ds_pdfs: xarray dataset with xk, pk values for selected coordinates
    """
    df = ds.to_dataframe()
    station = PVstation(instation.tilt(coords[0]), instation.azim, instation.tracking,
                        instation.capacity, instation.data_freq)
    station.coords = coords
    df = df.drop(['lon', 'lat'], axis=1)
    data_freq = station.data_freq

    for col in df.columns:
        if col not in ['global_horizontal', 'diffuse_fraction', 'temperature']:
            df.drop([col], axis=1, inplace=True)

    df = df.replace([np.inf, -np.inf], 0)

    # Annual and seasonal data are first upsampled to monthly values and then for each month the
    # corresponding number of days is drawn from the PDFs (Probability density functions)
    if data_freq == 'S':
        df = df.resample(rule='QS-DEC').bfill()

    df_all = pd.DataFrame()
    # Random days for each month are computed and stitched together to new dataframe:
    for j, row in df.iterrows():
        year = row.name.year
        stmon = row.name.month
        n_months = 1
        if data_freq == 'A':
            n_months = 12
        elif data_freq == 'S':
            n_months = 3
        rand_days_list = []
        temperatures = []
        monthlist = 2 * list(range(1, 13))
        for mon in monthlist[stmon-1:stmon+n_months-1]:
            days = monthrange(year, mon)[1]
            ds_pdfs_mon = ds_pdfs.sel(month=mon)
            rand_days = create_rand_month(xk=ds_pdfs_mon['xk'].values, pk=ds_pdfs_mon['pk'].values,
                                          n=monthrange(year, mon)[1])
            rand_days_list.extend(rand_days)
            if 'temperature in row':
                temperatures.extend(np.full(days, row['temperature']))
        if any(rand_days_list):
            rand_days_list = [q * (row['global_horizontal'] / np.mean(rand_days_list)) for q in rand_days_list]
        time_index = pd.date_range(start='{}-{}-01'.format(str(year), str(stmon)),
                                   periods=len(rand_days_list), freq='D')
        if 'temperature' in row:
            df_pdf = pd.DataFrame(data={'global_horizontal': rand_days_list, 'temperature': temperatures},
                                  index=time_index)
        else:
            df_pdf = pd.DataFrame(data={'global_horizontal': rand_days_list},
                                  index=time_index)
        df_pdf.index.name = 'time'
        df_all = pd.concat([df_all, df_pdf])

    pv = kd_and_gsee(df=df_all, station=station)
    if data_freq != 'S':
        pv = pv.resample(rule=data_freq).mean()
    elif data_freq == 'S':
        pv = pv.resample(rule='QS-DEC').mean()
    process_return_pv(pv, shr_mem, prog_mem, coords, i)


class PVstation:
    def __init__(self,tilt, azim, tracking, capacity, data_freq):
        self.azim = azim
        self.tilt = tilt
        self.tracking = tracking
        self.capacity = capacity
        self.coords = (0,0) #Format (lat, lon) as GSEE needs it like this
        self.data_freq = data_freq




