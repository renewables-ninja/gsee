#!/usr/bin/python

import gsee.climatedata_interface.interface as inter

basefolder = '/home/username/climate_data'

th_file = '{}/sis-split-years2011-monmean.nc'.format(basefolder)
df_file = '{}/df-split-years2011-monmean.nc'.format(basefolder)
at_file = '{}/tas-split-years2011-monmean.nc'.format(basefolder)

var_names = ['SIS', 'df', 'T2M']

outfile = '{}/outputs.nc4'.format(basefolder)

timeformat = 'other'

# A function of tilt depending on lat can be provided, or simply a fixed value returned:
def tilt_function(lat):
    return 0.35396 * lat + 16.84775

params = {'tilt': tilt_function, 'azimuth': 180, 'tracking': 0, 'capacity': 1000, 'data_freq': 'detect'}
use_pdfs = True
pdfs_file_path='/home/username/PDFs/MERRA2_rad3x3_2011-2015-PDFs_land_prox.nc4'

inter.run_interface(ghi_tuple=(th_file, var_names[0]), diffuse_tuple=(df_file, var_names[1]),
                    temp_tuple=(at_file, var_names[2]), outfile=outfile, params=params,
                    timeformat=timeformat, use_pdfs=use_pdfs, pdfs_file_path=pdfs_file_path)