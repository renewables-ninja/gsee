#!/usr/bin/python

import gsee.climdata_interface.interface as inter

# basefolder = '/home/johannes/Downloads/GSEE-interface test data'
basefolder = '/home/johannes/Downloads/sis-dni-tas-NN'
# basefolder = '/home/johannes/Downloads/pi-control-test-data'

th_file = '{}/sis-split-years2011-yearmean.nc'.format(basefolder)
# only makes sense with hourly data as otherwise it has to be approximated anyway:
df_file = '{}/df-split-years2011-daymean.nc'.format(basefolder)
at_file = '{}/tas-splityears2011-yearmean.nc'.format(basefolder)

# th_file = '{}/HadGEM2-AO_r1i1p1_rsds_20061231-20161231_EU.nc'.format(basefolder)
# th_file = '{}/rsds_Amon_CanESM2_piControl_r1i1p1_241101-251012.nc'.format(basefolder)
# th_file = '{}/rsds_Amon_MPI-ESM-P_piControl_r1i1p1_200001-219912.nc'.format(basefolder)
# df_file = '{}/df-2011-2015-NN-daymean'.format(basefolder)
# at_file = '{}/tas_Amon_CanESM2_piControl_r1i1p1_241101-251012.nc'.format(basefolder)
# at_file = '{}/tas_Amon_MPI-ESM-P_piControl_r1i1p1_200001-219912.nc'.format(basefolder)

var_names = ['SIS', 'df', 'T2M']

outfile = '{}/output-yearmean-pdfs-new-land3x3_prox.nc4'.format(basefolder)

timeformat = 'other' #'cmip5' # two options: 'cmip5-datestring': date as number e.g. 20071215.5 or 'other':whatever xarray reads in


# A function of tilt depending on lat can be privided, or simply a fixed value returned
def tilt_function(lat):
    return 0.353959636801573 * lat + 16.8477501393928
    # return 35

tilt = tilt_function
azimuth = 180
tracking = 0
capacity = 1

params =[tilt, azimuth, tracking, capacity]
data_freq = 'detect' # is either 'A', 'S', 'M', 'D', 'H' or 'detect' mostly detects everything but seasonal
use_PDFs = True
th_factor = 1/1000 #GSEE requires kW


th_tuple = (th_file, var_names[0])
df_tuple = (df_file, var_names[1])
at_tuple = (at_file, var_names[2])

inter.run_interface(th_tuple=th_tuple, df_tuple=df_tuple, at_tuple=at_tuple,
                        outfile=outfile, params=params, in_freq=data_freq, timeformat=timeformat,
                        use_PDFs=use_PDFs, th_factor=th_factor,
                        pdfs_file_path='gsee/climdata_interface/PDFs/MERRA2_rad3x3_2011-2015-PDFs_land_prox.nc4')

