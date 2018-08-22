#!/usr/bin/python

import gsee.climatedata_interface.interface as inter

basefolder = '/home/username/climate_data'


th_file = '{}/sis-split-years2011-monmean.nc'.format(basefolder)
df_file = '{}/df-split-years2011-monmean.nc'.format(basefolder)
at_file = '{}/tas-split-years2011-monmean.nc'.format(basefolder)

var_names = ['SIS', 'df', 'T2M']

outfile = '{}/outputs.nc4'.format(basefolder)

timeformat = 'other'

# A function of tilt depending on lat can be provided, or simply a fixed value returned
def tilt_function(lat):
    return 0.353959636801573 * lat + 16.8477501393928

tilt = tilt_function
azimuth = 180
tracking = 0
capacity = 1
in_freq = 'detect'
params = {'tilt': tilt, 'azimuth': azimuth, 'tracking': tracking, 'capacity': capacity, 'data_freq': in_freq}
use_pdfs = True
th_factor = 1/1000 # GSEE requires kW

inter.run_interface(th_tuple=(th_file, var_names[0]), df_tuple=(df_file, var_names[1]),
                    at_tuple=(at_file, var_names[2]), outfile=outfile, params=params,
                    timeformat=timeformat, use_pdfs=use_pdfs, th_factor=th_factor)
