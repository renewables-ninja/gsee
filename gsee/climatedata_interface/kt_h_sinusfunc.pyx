from libc.math cimport sin, cos, tan, acos, M_PI
import math as m
cimport numpy as np
import numpy as np

cpdef double kt_h(double gsc, double lat, double n, double h, double Eo, double sunrise_h, double glob_h):
    """
    Computes the atmospheric clearness index with the extra-terrestrial radiation
    at a given location based on:

    Parameters
    ----------
    gsc: float
        solar constant
    n: int
        day of year
    h: float
        hour of day
    Eo: float
        Eccentricity coefficient
    sunrise_h: float
        hour at which sunrise takes place
    glob_h: float
        global horizontal radiation at that location

    """
    cdef double H, w, Go, ws, sdec
    H = glob_h

    if H > 0:
        h = h + 0.5
        sdec = (M_PI/180)*(23.45) * sin((M_PI/180)*(360 * (284 + n) / 365))
        ws = -acos(-(tan(lat) * tan(sdec)))
        w = ws + (h - sunrise_h) * (M_PI/180)*(15)
        Go = gsc * Eo * (cos(lat) * cos(sdec) * cos(w) + sin(lat) * sin(sdec))

        if Go:
            return max(0, min(H / Go, 1))
    else:
        return np.nan

cpdef np.ndarray[double] apply_kt_h(double gsc, double lat, np.ndarray col_n, np.ndarray col_h, np.ndarray col_Eo, np.ndarray col_sunrise_h, np.ndarray col_glob_h):
    """
    Iterates over each row of the given dataframe and applies a funtionc The dataframe is given in the
    form of ndarrays for each column. This is much faster than pandas.DataFrame.iterrows.
    """
    cdef Py_ssize_t i, n = len(col_h)
    cdef np.ndarray[double] res = np.empty(n)
    for i in range(len(col_h)):
        res[i] = kt_h(gsc, lat, col_n[i], col_h[i], col_Eo[i], col_sunrise_h[i], col_glob_h[i])
    return res


cpdef csinus_func(double rise, double set, double h, double glob_h_day):
    """
    Calculates hourly irradiance following a sunusoidal function based on:

    Parameters
    ----------
    rise: float
     time of sunrise
    set: float
        time of sunset
    h: float
        hour at which to calculate irradiance
    glob_h_day: float
        total radiation over the entire day

    """
    cdef double dt
    h = h + 0.5

    if rise < set:
        dt = set - rise
        if (rise < h) & (h < set):
            return max(0, sin((M_PI / dt) * (h - rise)) *
                       ((glob_h_day * M_PI) / (2 * dt)))
        else:
            return 0
    else:
        dt = 24 - (rise-set)
        if h <= set:
            return max(0, sin((M_PI / dt) * (h + 24 - rise)) *
                       ((glob_h_day * M_PI) / (2 * dt)))
        elif h >= rise:
            return max(0, sin((M_PI / dt) * (h - rise)) *
                       ((glob_h_day * M_PI) / (2 * dt)))
        else:
            return 0


cpdef np.ndarray[double] apply_csinus_func(np.ndarray col_rise, np.ndarray col_set, np.ndarray col_h, np.ndarray col_glob_h_day):
    """
    Iterates over each row of the given dataframe and applies a funtionc The dataframe is given in the
    form of ndarrays for each column. This is much faster than pandas.DataFrame.iterrows.
    """
    cdef Py_ssize_t i, n = len(col_h)
    cdef np.ndarray[double] res = np.empty(n)
    for i in range(len(col_h)):
        res[i] = csinus_func(col_rise[i], col_set[i], col_h[i], col_glob_h_day[i])
    return res
