#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Cyclone tracks object, wind field models

@author: khan
"""
from __future__ import print_function
from .conversion import gc_distance, pa2mb, km2m, hpa2pa, knot2mps, ntm2m, ft2m
import pandas as pd
import numpy as np
from scipy import optimize
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from datetime import datetime, timedelta
import sys

def coriolis(lat):
    '''
    Calculate the coriolis parameter
    '''
    f = 2*7.292e-5*np.sin(np.deg2rad(lat))
    return(f)

def calc_rmax_s02(mslp):
    '''
    Calculates rmax as a function of central pressure as described in Silva 2002.

    mslp: float, central pressure in Pascal 

    Ref: Silva,  R., G. Georges, S. Paulo, B. Gustavo and B. G. D. Gabriel (2002).
    Oceanographic vulnerability to hurricanes on the Mexican coast.
    Pro-ceedings of 28th Conference on Coastal Engineering, 39-51. 
    '''
    try:
        mslp = pa2mb(mslp)
    except:
        raise Exception(f'mslp is a required input for S02 method of rmax calculation')
    
    rmax = 0.4785 * mslp - 413 # In Km
    rmax = km2m(rmax)

    return rmax

def calc_rmax_w04(vmax, lat):
    '''
    Calculates rmax as a function of the maximum velocity as described in 
    Willoughby and Rahn (2004) paper.

    vmax: float, m/s
    lat: float, m/s

    Ref: 
    Willoughby and Rahn (2004) Parametric Representation of the Primary Hurricane
    Vortex. Part I: Observations andEvaluation of the Holland (1980) Model, Monthly
    Wearher Review
    '''
    try:
        rmax = 51.6*np.exp(-0.0223*vmax + 0.0281*lat) # Km
    except:
        raise Exception(f'vmax and lat are required input for W04 method of rmax calculation')

    rmax = km2m(rmax)

    return(rmax)

def calc_rmax_e11(v, r, vmax, f, solver='fsolve', limit=[5000, 500000], step=100):
    '''
    Calculate maximum radius using Emanuel 2011 model. 

    v: float, known velocity information at the boundary layer, m/s
    r: float, known radial information corresponding to v, m
    vmax: float, known maximum velocity, m/s
    f: coriolis coefficient, taken at the center as it is small
    solver: solver type -
        fsolve: use scipy.optimize.fsolve
        scan: use linear scanning
    limit: limit for scanning in scan solver and limit[0] is x0 for fsolve
    step: stepping for scan solver
    vlimit: (vmin, vmax) limit to return a result, otherwise exception thrown

    Ref: Emanuel 2011, Lin and Chavas 2012, Krien et al. 2017
    '''

    resfunc = lambda rmax: v - (2*r*(vmax*rmax+0.5*f*rmax**2)/(rmax**2+r**2)-f*r/2)
    try:
        if solver=='scan':
            rm_range = np.arange(start=limit[0], stop=limit[1]+step, step=step)
            for rm in rm_range:
                res = resfunc(rm)
                if res < 0:
                    break
            rmax_solved = rm
        elif solver=='fsolve':
            rmax_solved = optimize.fsolve(func=resfunc, x0=limit[0])
    except:
        raise Exception('Solver failed')
    
    return(rmax_solved)

def calc_holland_B(vmax, pc, pn, rhoair, bmax=2.5, bmin=0.5):
    '''
    Calculates the simplified version of Holland's B parameters excluding the
    term with coriolis.

    vmax: Velocity of maximum wind at boundary layer, m/s
    pc: Central pressure, Pa
    pn: environmental pressure, Pa
    rhoair: Density of air kg/m**3
    bmax: maximum limit of B
    bmin: minimum limit of B
    '''
    B = (vmax**2)*rhoair*np.exp(1)/(pn-pc)

    if B<bmin:
        B = bmin
    elif B>bmax:
        B = bmax
    else:
        B = B
    
    return(B)

def calc_holland_B_full(vmax, rmax, pc, f, pn, rhoair, bmax=2.5, bmin=0.5):
    '''
    Calculates the holland B paramter using the full expression.

    vmax: Velocity of maximum wind at boundary layer, m/s
    rmax: radius of maximum wind, m
    pc: central pressure, Pa
    f: coriolis
    pn: Environmental pressure, 101325pa
    rhoair: density of air kg/m**3
    bmax: maximum limit of B
    bmin: minimum limit of B
    '''
    B = (vmax**2*rhoair*np.exp(1) + f*vmax*rmax*np.exp(1)*rhoair)/(pn-pc)

    if B<bmin:
        B = bmin
    elif B>bmax:
        B = bmax
    else:
        B = B

    return(B)

def calc_rmax_h80(v, r, pc, B, f, pn, rhoair, solver='fsolve', limit=[5000, 100000], step=100):
    '''
    Solve rmax with for a given r and v using Holland 1980 model.

    v: float, velocity in m/s
    r: float, radial distance corresponding to v, in m
    pc: float, central pressure, Pa
    B: float, Holland B parameter, calculable by calc_holland_B()
    f: float, coriolis parameter
    solver: solver to use - scan or fsolve (default)
    limit: limit for scan solver or starting point for fsolve
    step: scan solver stepping, in m
    '''

    resfunc = lambda rmax: v - (np.sqrt(B/rhoair*(rmax/r)**B*(pn-pc)*np.exp(-(rmax/r)**B)+(r*f/2)**2) - r*f/2)

    try:
        if solver=='scan':
            rm_range = np.arange(start=limit[0], stop=limit[1]+step, step=step)
            for rm in rm_range:
                res = resfunc(rm)
                if res < 0:
                    break
            rmax_solved = rm
        elif solver=='fsolve':
            rmax_solved = optimize.fsolve(func=resfunc, x0=limit[0])
    except:
        raise Exception('Solver failed')
    
    return(rmax_solved)

def calc_vcirc_j92(r, Rm, Vm):
    '''
    Calculate circular wind speed according to Jelesnianski et al. 1992 model. 
    It is also known as SLOSH: Sea, lake, and overland surges from hurricanes
    NOAA model.

    It is a simple model, and apprently when the coriolis is neglected (f -> 0)
    Emanuel 2011 model reduces to SLOSH model.

    r: float, radial distance (m)
    Rm: float, radius of maximum wind (m)
    Vm: float, maximum wind speed (m/s) 
    '''
    vcirc = (2*r*Rm*Vm)/(Rm**2+r**2)
    return(vcirc)

def calc_vcirc_h80(r, Rm, pc, B, pn, rhoair, f):
    '''
    Calculate circular wind speed based on Holland 1980 model.

    r: float, radial distance (m) where the circular wind speed is calculated
    Rm: float, radius of maximum wind (m)
    pc: float, central pressure
    B: float, Holland B parameter, can be calculated using calc_holland_B_full()
    pn: float, nominal pressure outide of the storm
    rhoair: density of air km/m**3
    f: coriolis parameter, can be calculated with coriolis() function
    '''
    r = r + 1e-8 # Avoid divided by zero issue for r==0
    vcirc = np.sqrt((Rm/r)**B * (B/rhoair) * (pn-pc) * np.exp(-(Rm/r)**B) + (r*f/2)**2) - (r*f/2)
    return(vcirc)

def calc_vcirc_h80c(r, Rm, pc, B, pn, rhoair):
    '''
    Holland 1980 model with cyclostropic approximation. In this approximation
    all the terms related to coriolis is neglected (f->0)

    r: float, radial distance (m) where the circular wind speed is calculated
    Rm: float, radius of maximum wind (m)
    pc: float, central pressure
    B: float, Holland B parameter, can be calculated using calc_holland_B_full()
    pn: float, nominal pressure outide of the storm
    rhoair: density of air km/m**3
    '''
    r = r + 1e-8
    vcirc = np.sqrt((Rm/r)**B * (B/rhoair) * (pn-pc) * np.exp(-(Rm/r)**B))
    return(vcirc)

def calc_vcirc_w06(r, Rm, Vm, n=0.79, X=243000):
    '''
    Calculate circular wind speed using Willoughby et al. 2006 model. 

    r: float, radial distance in (m)
    Rm: float, radius of maximum wind (m)
    n: power of increasing profile, default n=0.79
    X: distance to which extend the profile, (m) default 243km (243000m)
    '''
    if r <= Rm:
        vcirc = Vm * (r/Rm)**n
    else:
        vcirc = Vm * np.exp(-(r-Rm)/X)

    return(vcirc)

def calc_vcirc_e04(r, Rm, Vm, b=0.25, m=1.6, n=0.9, R0=420000):
    '''
    Calculate circular wind speed using Emanuel 2004 model. 

    r: float, radial distance (m)
    Rm: float, radisu of maximum wind (m)
    b: constant, default 0.25
    m: constant, default 1.6
    n: constant, default 0.9
    R0: distance, (m), default 420000m (420km)
    '''
    multiplier = ((1-b)*(n+m)/(n+m*(r/Rm)**(2*(n+m)))) + (b*(1+2*m)/(1+2*m*(r/Rm)**(2*m+1)))
    vcirc = Vm * ((R0-r)/(R0-Rm)) * (r/Rm)**m * np.sqrt(multiplier)

    return(vcirc)

def calc_vcirc_e11(r, Rm, Vm, f):
    '''
    Calculate circular wind speed using Emanuel 2011 model. The model equation is
    given in Lin and Chavas 2012.

    r: float, radial distance (m)
    Rm: float, radius of maximum wind (m)
    Vm: float, maximum wind speed (m/s)
    f: coriolis, can be calc by coriolis() function
    '''
    vcirc = 2*r*(Rm*Vm+0.5*f*Rm**2)/(Rm**2+r**2) - r*f/2

    return(vcirc)

def calc_vcirc_m16(r, Rm, Vm, n=0.6):
    '''
    Calculate circular wind speed using Murty et al. 2016 model, developed for 
    indian ocean.

    r: float, radial distance (m)
    Rm: float, radius of maximum wind (m)
    Vm: float, maximum wind speed (m/s)
    n: power, default is 0.6
    '''
    vcirc = Vm * ((2*r*Rm)/(Rm**2+r**2))**n
    return(vcirc)

def calc_mslp_h80(r, Rm, pc, B, pn):
    '''
    Calculate mean-sea-level pressure based using Holland 1980 model.
    r: radial distance
    '''
    r = r + 1e-8
    mslp = (pn-pc)*np.exp(-(Rm/r)**B) + pc
    return(mslp)

class Record(dict):
    def __init__(self, *args, **kwargs):
        '''
        A recrod object takes keyworded input as arguments by entending the python
        dictionary object. 

        The required fields are - 
            : timestamp:    datetime, pd.Datetimeindex
            : lon:          longitude, 0-359, float
            : lat:          latitude, -180, 180, float
            : mslp:         central pressure, Pa, float
            : vmax:         maximum velocity, m/s, float
        
        The optional (but recommended) fields are - 
            : rmax:         radius of maximum wind, m, float
            : vinfo:        list of velocity, m/s, list or numpy array, size n
            : radinfo:      2d list of radial info, m, list or numpy array, size nx4
            : ustorm:       speed of storm in x-direction, m/s
            : vstorm:       speed of strom in y-direction, m/s
        '''
        req_kw = ['timestamp', 'lon', 'lat', 'mslp', 'vmax']
        opt_kw = ['rmax', 'vinfo', 'radinfo', 'ustorm', 'vstorm']

        try:
            assert np.all([kw in kwargs for kw in req_kw])
        except:
            raise Exception(f'All required fields are not provided')

        for kw in opt_kw:
            if kw not in kwargs:
                kwargs[kw] = np.nan

        # Correcting datetime and convert to pandas datetime object
        allowed_datetime = (datetime, pd.DatetimeIndex, str)
        try:
            assert isinstance(kwargs['timestamp'], allowed_datetime)
        except:
            raise Exception(f'timestamp must be parsable by pd.to_datetime')
        else:
            kwargs['timestamp'] = pd.to_datetime(kwargs['timestamp'])

        # Initiate the dictionary
        super(Record, self).__init__(*args, **kwargs)
    
    def __setitem__(self, key, value):
        super(Record,self).__setitem__(key, value)

    @property
    def center(self):
        return((self['lon'], self['lat']))

    def gen_radial_fields(self, fraction=0.56, angle=19.2, swrf=0.9):
        '''
        Generate the interpolator for radial field for exisiting radial informations.
        To get correct radial field, atmospheric background is removed and
        the amount to be removed is controlled by fraction, and angle.  

        Arguments:
            fraction: float, fraction of translation speed to remove
            angle: float, angle of translation velocity change in degree
            swrf: float, surface wind reduction factor

        Due to translation a fraction of the wind-speed is embadded to the axysymmetric
        wind structure. To get the radial wind structure, we need to remove this
        translation velocity from the recorded wind velocity.
        
        The fraction is historically taken as unity (1). However, as shown in 
        lin and chavas (2012), more statistically consistent value of this fraction
        is 0.56 (default)

        Similarly, the translation is not fully forward (angle=0), rather the 
        background wind is slightly on southerly direction if we consider the
        storm is westerly. The angle is found around 19.2 degrees from statistical
        analysis. Thus the background wind is rotated anti-clockwise and needs 
        to be updated before applying as fraction to the wind values.

        In the advisories, radial fields are defined at 10m level, whereas 
        the analytical fields are defined at the boundary layer. Thus the velocity
        is needed to be divided by SWRF to shift it to boundary layer and multiplied
        by SWRF to get it back to 10m level.
        '''
        # Rotating ustorm vstorm by 19.2 degree anti-clockwise
        # Same operation as rotating a cartesian coordinate by 19.2 degree
        angle_rad = np.deg2rad(angle)
        if np.any(np.isnan([self['ustorm'], self['vstorm']])):
            ustorm = 0
            vstorm = 0
        else:
            ustorm = self['ustorm']*np.cos(angle_rad) - self['vstorm']*np.sin(angle_rad)
            vstorm = self['ustorm']*np.sin(angle_rad) + self['vstorm']*np.cos(angle_rad)

        # Apply correction to vmax for 4 quadrant clockwise from 0N
        # Careful about the sin/cos from north
        #            N
        #            | t /
        #            | /
        #    W ------*------- E
        #            |
        #            |
        #            S
        theta = np.linspace(0, 2*np.pi, 5)
        vmax_x = self['vmax'] * np.sin(theta)*(-1) - fraction*ustorm 
        vmax_y = self['vmax'] * np.cos(theta) - fraction*vstorm
        vmax_amp = np.sqrt(vmax_x**2 + vmax_y**2)/swrf
        self['fvmax'] = interp1d(theta, vmax_amp)

        # Apply correction to vinfo for 4 quadrant
        fvinfo = np.array([])
        fradinfo = np.array([])
        for i, vinfo in enumerate(np.atleast_1d(self['vinfo'])):
            if np.isnan(vinfo):
                self['vinfo'] = np.nan
                self['radinfo'] = np.nan
            else:
                vinfo_x = vinfo * np.sin(theta)*(-1) - fraction*ustorm
                vinfo_y = vinfo * np.cos(theta) - fraction*vstorm
                vinfo_amp = np.sqrt(vinfo_x**2 + vinfo_y**2)/swrf
                vinfo_func = interp1d(theta, vinfo_amp)
                fvinfo = np.append(fvinfo, vinfo_func)

                radinfo = np.append(self['radinfo'][i], self['radinfo'][i][0])
                radinfo_func = interp1d(theta, radinfo)
                fradinfo = np.append(fradinfo, radinfo_func)
        
        self['fvinfo'] = fvinfo
        self['fradinfo'] = fradinfo

        return(self)

    def calc_rmax(
        self, 
        methods=['H80', 'E11'], 
        use_rmax_info=False, 
        vlimit=[20, np.inf],
        kw_atmos={'pn':101325, 'rhoair':1.15},
        kw_h80={'bmax':2.5, 'bmin':0.5, 'solver':'fsolve', 'limit':[5000, 500000], 'step':100},
        kw_e11={'solver':'fsolve', 'limit':[5000, 500000], 'step':100}
    ):
        '''
        Calculate Radius of maximum wind based on a given method on the selected
        radial informations.

        methods: list, list of methods to try one after another
        use_rmax_info: bool, existing rmax to be used directly or not
        vlimit: list of maximum limit of v for method to be used, 
                last one must be np.inf, vlimit is right open )
        kw_atmos: dict, atmospheric information, generally needed for H80 model
        kw_h80: dict, solver options for H80 model
        kw_e11: dict, solver options for E11 model

        Following methods are implemented - 
            'E11' : Emanuel 2011 model as described in Lin and Chavas 2012
            'H80' : Holland 1980 model based on radial info
            'S02' : Silva et al. 2002 based on regression of central pressure
                    rmax = 0.4785 * Pc (mb) - 413 (km)
            'W04' : Willoughby and Rahn (2004) regression of Vmax
                    rmax = 51.6*exp(-0.0223*Vmax + 0.0281*lat) (km)

        Models to be implemented in the future - 
            'H80c' : Holland 1980c (f related values are removed)
            'S92' : Slosh model, by jeleniaski et al . 1992
            'E04' : Emanuel 2004 model
            'M16' : Murty et al 2016 model
            'W06' : Willoughby et al. 2006 model 
        
        '''
        methods = np.atleast_1d(methods)

        calc_rmax = {
            'E11': calc_rmax_e11,
            'H80': calc_rmax_h80,
            'S02': calc_rmax_s02,
            'W04': calc_rmax_w04
        }
        
        try:
            assert len(np.atleast_1d(vlimit)) == len(methods)
        except:
            raise Exception(f'vlimit must be the size of methods.')

        vlimit_min = np.append(0, vlimit)[0:-1] # Starts from 0 m/s
        vlimit_max = vlimit

        if np.all([~np.isnan(self['rmax']), use_rmax_info]):
            # Use the provided vmax
            theta = np.linspace(0, 2*np.pi, 5)
            rmax = np.ones_like(theta)*self['rmax']
            frmax = interp1d(theta, rmax)
            self['frmax'] = frmax
        elif np.all(np.isnan(self['vinfo'])):
            theta = np.linspace(0, 2*np.pi, 5)
            if not np.isnan(self['mslp']):
                # Use S02 regression method for rmax
                rmax = np.ones_like(theta)*calc_rmax_s02(mslp=self['mslp'])
            elif not np.isnan(self['vmax']):
                # Use W04 regression method for rmax
                rmax = np.ones_like(theta)*calc_rmax_w04(vmax=self['vmax'], lat=self['lat'])
            
            frmax = interp1d(theta, rmax)
            self['frmax'] = frmax
        else:
            frmax = np.array([]) # length of fvinfo or atleast 1
            rmax_method = np.array([]) # Keeping the rmax_method used
            theta = np.linspace(0, 2*np.pi, 5)
            
            # Radial info is available and rmax is to be calculated from radinfo
            for fv, fr in zip(self['fvinfo'], self['fradinfo']):
                rmax_fv_theta = np.ones_like(theta) # Placeholder
                
                # Iterating over all the values interpolated by theta
                for i, thetai in enumerate(theta):
                    for j, method in enumerate(methods):
                        try:
                            # Check the vlimit_min vlimit_max
                            assert fv(thetai) >= vlimit_min[j]
                            assert fv(thetai) < vlimit_max[j]
                            
                            # Trying each methods
                            if method == 'E11':
                                kwargs = {
                                    'v':fv(thetai), 
                                    'r':fr(thetai), 
                                    'vmax':self['fvmax'](thetai), 
                                    'f':coriolis(self['lat']), 
                                    'solver':kw_e11['solver'], 
                                    'limit':kw_e11['limit'], 
                                    'step':kw_e11['step']
                                }
                                rmax_fv_theta[i] = calc_rmax[method](**kwargs)

                            if method == 'H80':
                                # First calculate holland B parameter
                                kwargs = {
                                    'vmax':self['fvmax'](thetai),
                                    'pc':self['mslp'],
                                    'pn':kw_atmos['pn'],
                                    'rhoair':kw_atmos['rhoair'],
                                    'bmax':kw_h80['bmax'],
                                    'bmin':kw_h80['bmin']
                                }
                                B = calc_holland_B(**kwargs)

                                # Then calculate the rmax
                                kwargs = {
                                    'v':fv(thetai), 
                                    'r':fr(thetai), 
                                    'pc':self['mslp'], 
                                    'B':B, 
                                    'f':coriolis(self['lat']), 
                                    'pn':kw_atmos['pn'], 
                                    'rhoair':kw_atmos['rhoair'], 
                                    'solver':kw_h80['solver'], 
                                    'limit':kw_h80['limit'], 
                                    'step':kw_h80['step']
                                }
                                rmax_fv_theta[i] = calc_rmax[method](**kwargs)

                            if method == 'S02':
                                kwargs = {
                                    'mslp':self['mslp']
                                }
                                rmax_fv_theta[i] = calc_rmax[method](**kwargs)

                            if method == 'W04':
                                kwargs = {
                                    'vmax':self['fvmax'](thetai),
                                    'lat':self['lat']
                                }
                                rmax_fv_theta[i] = calc_rmax[method](**kwargs)                            

                            # When successful break the loop
                            break
                        except:
                            # Otherwise continue with the methods
                            continue
                
                # For a particular vinfo create the interpolation function
                # append to frmax
                frmax_fv = interp1d(theta, rmax_fv_theta)
                frmax = np.append(frmax, frmax_fv)
            
            # Save to Record dictionary
            self['frmax'] = frmax  
            self['rmax_method'] = rmax_method
        
        return(self)        

    def calculate_wind(
        self, 
        at, 
        methods=['E11','H80'],
        rmax_frac=[2, np.inf],
        rmax_select='mean',
        kw_corr={'fraction':0.56, 'angle':19.2, 'swrf':0.9, 'tfac':0.88},
        kw_atmos={'pn':101325, 'rhoair':1.15},
        kw_h80={'bmax':2.5, 'bmin':0.5},
        kw_e04={'b':0.25, 'm':1.6, 'n':0.9, 'R0':420000},
        kw_w06={'n':0.79, 'X':243000},
        kw_m16={'n':0.6}
    ):
        '''
        Calculate wind field using given method till a fractional distance of 
        rmax.

        at: (r, theta) location where the wind is calculated,
            r, float, distance in m 
            theta, float, is -2*np.pi, 2*np.pi radians
            Essentially theta is expected to be output from np.arctan2(y,x)
            Theis counter-clockwise from x-axis angle is converted to a clockwise
            angle from y axis to match the interpolation grid of the storm paramters. 
        methods: array, list of methods to be used. Currently implemented methods
                are - H80, H80c, J92, W06, E04, E11, M16
        rmax_frac: array, till which fraction of rmax, the method to be used,
                np.inf for whole
        rmax_select: which rmax to select, int, str
                    'mean': mean value of the rmax
                    'nearest': rmax calculated from nearest frmax
                    'linear': rmax calculated from a linear interpolation
                    int: number corresponding to selected rmax >1
        kw_corr: corrections applied for translation and surface wind reduction
                fraction: fraction of translation wind, 0.56 default
                angle: angle of ratation, 19.2 degree default
                swrf: surface wind reduction factor, 0.9 default
                tfac: convertion factor to from x minute to 10 minute wind
                    0.88 for conversion from 1minute to 10minute
        kw_atmos: constant atmospheric values
            pn: nominal or environmental pressure, default 101325 Pa
            rhoair: air density, default 1.15 km/m^3
        kw_h80: extra argument for H80 model
            bmin: Minimum B value
            bmax: Maximum B value
        kw_e04: extra argument for E04 model
            b: default 0.25
            m: default 1.6
            n: default 0.9
            R0: default 420000m (420km)
        kw_w06: extra argument for W06 model
            n: default 0.79
            X: default 243000m (243km)
        kw_m16: extra argument for M16 model
            n: default 0.6
        '''
        try:
            r, theta_input = at
        except:
            raise Exception(f'the at must be in (r, theta) as list/array of size 2')
        
        # Convert theta from x-axis counter clock to y-axis clock wise
        theta = -1*theta_input + np.pi/2

        # Theta -180:180 to 0:360 format, clockwise from 0N
        if theta_input < 0:
            theta = 2*np.pi + theta_input
        else:
            theta = theta_input

        calc_vcirc = {
            'H80':calc_vcirc_h80,
            'H80c':calc_vcirc_h80c,
            'J92':calc_vcirc_j92,
            'W06':calc_vcirc_w06,
            'E04':calc_vcirc_e04,
            'E11':calc_vcirc_e11,
            'M16':calc_vcirc_m16
        }

        # Calculate vmax for further calculation
        vmax = self['fvmax'](theta)

        # Find appropriate rmax function to be used
        # and calculate rmax
        rmax_select_methods_available = ['mean', 'nearest', 'linear']

        if isinstance(rmax_select, str):
            try:
                assert rmax_select in rmax_select_methods_available

                if rmax_select=='mean':
                    rmax = np.mean([f(theta) for f in np.atleast_1d(self['frmax'])])
                
                if rmax_select=='nearest':
                    try:
                        radinfo = np.array([radi(theta) for radi in self['fradinfo']])
                        radnn = np.argmin(np.abs(radinfo-r))
                        rmax = np.array([f(theta) for f in np.atleast_1d(self['frmax'])])[radnn]
                    except:
                        rmax = np.atleast_1d(self['frmax'])[0](theta)
                        raise Warning('nearest not possible, first rmax selected')

                if rmax_select=='linear':
                    try:
                        # x field from -inf to +inf
                        radinfo = np.array([radi(theta) for radi in self['fradinfo']])
                        radinfo = np.append(-np.inf, radinfo)
                        radinfo = np.append(radinfo, np.inf)
                        # y field 
                        rmaxinfo = np.array([f(theta) for f in np.atleast_1d(self['frmax'])])
                        rmaxinfo = np.append(rmaxinfo[0], rmaxinfo)
                        rmaxinfo = np.append(rmaxinfo, rmaxinfo[-1])
                        int_f = interp1d(radinfo, rmaxinfo)
                        rmax = int_f(r)
                    except:
                        rmax = np.atleast_1d(self['frmax'])[0](theta)
                        raise Warning('linear not possible, first rmax selected')
            except:
                rmax = np.atleast_1d(self['frmax'])[0](theta)
                raise Warning(f'Wrong keyword for rmax method. First frmax is used')
        elif isinstance(rmax_select, int):
            try:
                np.array([f(theta) for f in np.atleast_1d(self['frmax'])])[rmax_select]
            except:
                rmax = np.atleast_1d(self['frmax'])[0](theta)
                raise Warning('Wrong rmax index. First frmax is used')
        else:
            rmax = np.atleast_1d(self['frmax'])[0](theta)
            raise Warning('Wrong rmax selection keyword/index. First frmax is used')

        # Now check methods and rmax_frac and apply method as required
        # Avoid wrong input of rmax_frac
        try:
            assert len(rmax_frac) == len(methods)
        except:
            raise Exception('rmax_frac must corresponds to each listed method')
        else:
            rmax_frac = np.atleast_1d(rmax_frac)
        
        rlim_min = np.append(0, rmax_frac)[0:-1]*rmax # Starts from 0
        rlim_max = rmax_frac*rmax

        for i, method in enumerate(methods):
            try:
                assert r >= rlim_min[i]
                assert r < rlim_max[i]

                if method == 'H80':
                    kwargs = {
                        'vmax':vmax, 
                        'rmax':rmax,
                        'pc':self['mslp'],
                        'f':coriolis(self['lat']),
                        'pn':kw_atmos['pn'],
                        'rhoair':kw_atmos['rhoair'],
                        'bmax':kw_h80['bmax'],
                        'bmin':kw_h80['bmin']
                    }
                    B = calc_holland_B_full(**kwargs)
                    kwargs = {
                        'r':r,
                        'Rm':rmax,
                        'pc':self['mslp'],
                        'B':B,
                        'pn':kw_atmos['pn'],
                        'rhoair':kw_atmos['rhoair'],
                        'f':coriolis(self['lat'])
                    }
                    vcirc = calc_vcirc[method](**kwargs)
                
                if method=='H80c':
                    kwargs = {
                        'vmax':vmax, 
                        'pc':self['mslp'],
                        'pn':kw_atmos['pn'],
                        'rhoair':kw_atmos['rhoair'],
                        'bmax':kw_h80['bmax'],
                        'bmin':kw_h80['bmin']
                    }
                    B = calc_holland_B(**kwargs)
                    kwargs = {
                        'r':r,
                        'Rm':rmax,
                        'pc':self['mslp'],
                        'B':B,
                        'pn':kw_atmos['pn'],
                        'rhoair':kw_atmos['rhoair']
                    }
                    vcirc = calc_vcirc[method](**kwargs)

                if method=='J92':
                    kwargs = {
                        'r': r,
                        'Rm':rmax,
                        'Vm':vmax
                    }
                    vcirc = calc_vcirc[method](**kwargs)

                if method=='W06':
                    kwargs = {
                        'r':r,
                        'Rm':rmax,
                        'Vm':vmax,
                        'n':kw_w06['n'],
                        'X':kw_w06['X']
                    }
                    vcirc = calc_vcirc[method](**kwargs)

                if method=='E04':
                    kwargs = {
                        'r':r,
                        'Rm':rmax,
                        'Vm':vmax,
                        'b':kw_e04['b'],
                        'm':kw_e04['m'],
                        'n':kw_e04['n'],
                        'R0':kw_e04['R0']
                    }
                    vcirc = calc_vcirc[method](**kwargs)
                    if vcirc <= 0:
                        vcirc = 0

                if method=='E11':
                    kwargs = {
                        'r':r,
                        'Rm':rmax,
                        'Vm':vmax,
                        'f':coriolis(self['lat'])
                    }
                    vcirc = calc_vcirc[method](**kwargs)
                    if vcirc <= 0:
                        vcirc = 0

                if method=='M16':
                    kwargs = {
                        'r':r,
                        'Rm':rmax,
                        'Vm':vmax,
                        'n':kw_m16['n']
                    }
                    vcirc = calc_vcirc[method](**kwargs)
                break
            except:
                continue
        
        # Calculating u,v wind with translation correction
        vcirc = vcirc * kw_corr['swrf']

        u = -vcirc*r*np.sin(theta_input)/np.max([r, 1e-8]) # 1e-8 avoids x/0
        v = vcirc*r*np.cos(theta_input)/np.max([r, 1e-8])

        utrans = self['ustorm']*np.cos(np.deg2rad(kw_corr['angle'])) - self['vstorm']*np.sin(np.deg2rad(kw_corr['angle']))
        vtrans = self['ustorm']*np.sin(np.deg2rad(kw_corr['angle'])) + self['vstorm']*np.cos(np.deg2rad(kw_corr['angle']))

        try:
            assert np.logical_not(np.any(np.isnan(utrans)))
            assert np.logical_not(np.any(np.isnan(vtrans)))

            u = u + kw_corr['fraction']*utrans
            v = v + kw_corr['fraction']*vtrans
        except:
            u = u
            v = v

        u = u * kw_corr['tfac']
        v = v * kw_corr['tfac']

        return(u, v)
    
    def calculate_pressure(
        self,
        at,
        methods=['H80'],
        rmax_frac= [np.inf],
        rmax_select='mean',
        kw_atmos={'pn':101325, 'rhoair':1.15},
        kw_h80={'bmax':2.5, 'bmin':0.5}
    ):
        '''
        Calculate pressure field using given method till a fractional distance of 
        rmax.

        at: (r, theta) location where the wind is calculated,
            r, float, distance in m 
            theta, float, is -2*np.pi, 2*np.pi radians
            Essentially theta is expected to be output from np.arctan2(y,x)
            This is counter-clockwise from x-axis angle is converted to a clockwise
            angle from y axis to match the interpolation grid of the storm paramters. 
        methods: array, list of methods to be used. Currently implemented methods
                are - H80, H80c
        rmax_frac: array, till which fraction of rmax, the method to be used,
                np.inf for whole
        rmax_select: which rmax to select, int, str
                    'mean': mean value of the rmax
                    'nearest': rmax calculated from nearest frmax
                    'linear': rmax calculated from a linear interpolation
                    int: number corresponding to selected rmax >1
        kw_atmos: constant atmospheric values
            pn: nominal or environmental pressure, default 101325 Pa
            rhoair: air density, default 1.15 kg/m^3
        kw_h80: extra argument for H80 model
            bmin: min value of B
            bmax: max value of B
        '''
        try:
            r, theta_input = at
        except:
            raise Exception(f'the at must be in (r, theta) as list/array of size 2')
        
        # Convert theta from x-axis counter clock to y-axis clock wise
        theta = -1*theta_input + np.pi/2

        # Theta -180:180 to 0:360 format, clockwise from 0N
        if theta_input < 0:
            theta = 2*np.pi + theta_input
        else:
            theta = theta_input

        calc_mslp = {
            'H80':calc_mslp_h80,
            'H80c':calc_mslp_h80 # Only B calculation differs
        }

        # Calculate vmax for further calculation
        vmax = self['fvmax'](theta)

        # Find appropriate rmax function to be used
        # and calculate rmax
        rmax_select_methods_available = ['mean', 'nearest', 'linear']

        if isinstance(rmax_select, str):
            try:
                assert rmax_select in rmax_select_methods_available

                if rmax_select=='mean':
                    rmax = np.mean([f(theta) for f in np.atleast_1d(self['frmax'])])
                
                if rmax_select=='nearest':
                    try:
                        radinfo = np.array([radi(theta) for radi in self['fradinfo']])
                        radnn = np.argmin(np.abs(radinfo-r))
                        rmax = np.array([f(theta) for f in np.atleast_1d(self['frmax'])])[radnn]
                    except:
                        rmax = np.atleast_1d(self['frmax'])[0](theta)
                        raise Warning('nearest not possible, first rmax selected')

                if rmax_select=='linear':
                    try:
                        # x field from -inf to +inf
                        radinfo = np.array([radi(theta) for radi in self['fradinfo']])
                        radinfo = np.append(-np.inf, radinfo)
                        radinfo = np.append(radinfo, np.inf)
                        # y field 
                        rmaxinfo = np.array([f(theta) for f in np.atleast_1d(self['frmax'])])
                        rmaxinfo = np.append(rmaxinfo[0], rmaxinfo)
                        rmaxinfo = np.append(rmaxinfo, rmaxinfo[-1])
                        int_f = interp1d(radinfo, rmaxinfo)
                        rmax = int_f(r)
                    except:
                        rmax = np.atleast_1d(self['frmax'])[0](theta)
                        raise Warning('linear not possible, first rmax selected')
            except:
                rmax = np.atleast_1d(self['frmax'])[0](theta)
                raise Warning(f'Wrong keyword for rmax method. First frmax is used')
        elif isinstance(rmax_select, int):
            try:
                np.array([f(theta) for f in np.atleast_1d(self['frmax'])])[rmax_select]
            except:
                rmax = np.atleast_1d(self['frmax'])[0](theta)
                raise Warning('Wrong rmax index. First frmax is used')
        else:
            rmax = np.atleast_1d(self['frmax'])[0](theta)
            raise Warning('Wrong rmax selection keyword/index. First frmax is used')

        # Now check methods and rmax_frac and apply method as required
        # Avoid wrong input of rmax_frac
        try:
            assert len(rmax_frac) == len(methods)
        except:
            raise Exception('rmax_frac must corresponds to each listed method')
        else:
            rmax_frac = np.atleast_1d(rmax_frac) # accomodates * of np.inf
        
        rlim_min = np.append(0, rmax_frac)[0:-1]*rmax # Starts from 0
        rlim_max = rmax_frac*rmax

        for i, method in enumerate(methods):
            try:
                assert r >= rlim_min[i]
                assert r < rlim_max[i]

                if method == 'H80':
                    kwargs = {
                        'vmax':vmax, 
                        'rmax':rmax,
                        'pc':self['mslp'],
                        'f':coriolis(self['lat']),
                        'pn':kw_atmos['pn'],
                        'rhoair':kw_atmos['rhoair'],
                        'bmax':kw_h80['bmax'],
                        'bmin':kw_h80['bmin']
                    }
                    B = calc_holland_B_full(**kwargs)
                    kwargs = {
                        'r':r,
                        'Rm':rmax,
                        'pc':self['mslp'],
                        'B':B,
                        'pn':kw_atmos['pn']
                    }
                    mslp = calc_mslp[method](**kwargs)
                
                if method=='H80c':
                    kwargs = {
                        'vmax':vmax, 
                        'pc':self['mslp'],
                        'pn':kw_atmos['pn'],
                        'rhoair':kw_atmos['rhoair'],
                        'bmax':kw_h80['bmax'],
                        'bmin':kw_h80['bmin']
                    }
                    B = calc_holland_B(**kwargs)
                    kwargs = {
                        'r':r,
                        'Rm':rmax,
                        'pc':self['mslp'],
                        'B':B,
                        'pn':kw_atmos['pn']
                    }
                    mslp = calc_mslp[method](**kwargs)
                
                break
            except:
                continue
        
        return(mslp)
    
    def __str__(self):
        repr_str = f'\t'.join([str(self[key]) for key in self])
        return(repr_str)

class Track(object):
    def __init__(self, records):
        '''
        Take a record or an array of record and provide track related functionalities.
        '''
        try:
            assert isinstance(records, (Record, np.ndarray))
        except:
            raise Exception(f'Records must be a single or an array of records')

        self.records = np.atleast_1d(records)

        try:
            assert np.all([isinstance(i, Record) for i in self.records])
        except:
            raise Exception(f'The records must be an array of Record object')

        self.timeindex = pd.to_datetime([record['timestamp'] for record in self.records])

        self.sort() # To put all records in ascending order
        self.calc_translation() # Recalculate translation speed

    def __iter__(self):
        '''
        Called and return the timeindex for invoke like - for t in track
        '''
        return iter(self.timeindex)

    def __getitem__(self, key):
        '''
        Get an item at a given timeindex
        '''
        if isinstance(key, int):
            track = Track(self.records[key])
        elif isinstance(key, np.ndarray):
            try:
                np.all([isinstance(i, int) for i in key])
            except:
                raise Exception(f'Integer indexing array expected')
            
            track = Track(self.records[key])
        elif isinstance(key, slice):
            track = Track(self.records[key.start:key.stop:key.step])
        else:
            try:
                key = pd.to_datetime(key)
            except:
                raise Exception(f'Accessor must be parsable by pd.to_datetime')

            track = Track(self.records[self.timeindex == key])

        return track

    def __setitem__(self, key, value):
        '''
        Set an item at a given time index
        '''
        try:
            key = pd.to_datetime(key)
        except:
            raise Exception(f'Accessor must be parsable by pd.to_datetime')

        self.records[self.timeindex == key] = value

    def __contains__(self, key):
        '''
        Implements checking of a record
        '''
        try:
            key = pd.to_datetime(key)
        except:
            key = key
        
        return key in self.timeindex

    def __getattr__(self, name):
        '''
        Implements accessing the the dictionary objects as array.
        '''
        try:
            attr = np.array([record[name] for record in self.records])
        except:
            raise Exception(f'{name} not found in the records')
        
        return attr

    def sort(self):
        '''
        Apply time sorting and sort the records
        '''
        isort = np.argsort(self.timeindex)
        self.timeindex = self.timeindex[isort]
        self.records = self.records[isort]

    def calc_translation(self):
        '''
        Calculate and update the ustorm, vstorm fields.
        '''
        for i in np.arange(0, len(self.records)-1):
            dt = (self.timeindex[i+1] - self.timeindex[i]).total_seconds()
            dtrans_x, dtrans_y = gc_distance(
                of_x = self.records[i+1]['lon'],
                of_y = self.records[i+1]['lat'],
                origin_x = self.records[i]['lon'],
                origin_y = self.records[i]['lat']
            )
            self.records[i]['ustorm'] = dtrans_x/dt
            self.records[i]['vstorm'] = dtrans_y/dt

            # For the last time step, we are keeping it to the same
            self.records[-1]['ustorm'] = self.records[-2]['ustorm']
            self.records[-1]['vstorm'] = self.records[-2]['vstorm']

    def append(self, records):
        try:
            assert isinstance(records, (Record, np.array))
        except:
            raise Exception(f'Records must be a single or an array of records')

        records = np.atleast_1d(records)

        try:
            assert np.all([isinstance(i, Record) for i in records])
        except:
            raise Exception(f'The records must be an array of Record object')

        self.records = np.append(self.records, records)
        self.timeindex = pd.to_datetime([record.timestamp for record in self.records])
        self.sort() # To put all record in ascending order
        self.calc_translation() # Recalculate translation speed

    def interpolate(self, at, **kwargs):
        try:
            at = pd.to_datetime(at, **kwargs)
        except:
            raise Exception(f'`at` must be parsable by pd.to_datetime')

        try:
            assert at <= self.timeindex[-1]
            assert at >= self.timeindex[0]
        except:
            raise Exception(f'Out of interpolation range')

        # Calculate the corresponding indices
        i_right = np.searchsorted(a=self.timeindex, v=at, side='left')

        if i_right == 0:
            i_left = 0
        else:
            i_left = i_right - 1

        # Calculate the corresponding weights
        v_left, v_right = self.timeindex[[i_left, i_right]]
        
        if(i_left < i_right):
            td_right = (v_right - at).total_seconds() # Timedelta to seconds
            td_total =  (v_right - v_left).total_seconds() # Timedelta to seconds
            w_left = td_right/float(td_total)
            w_right = 1-w_left
        else:
            w_left = float(1)
            w_right = float(0)

        # Create Record for the necessary fields with direct interpolation
        int_record = Record(
            timestamp=at,
            lon=self.records[i_left]['lon']*w_left + self.records[i_right]['lon']*w_right,
            lat=self.records[i_left]['lat']*w_left + self.records[i_right]['lat']*w_right,
            mslp=self.records[i_left]['mslp']*w_left + self.records[i_right]['mslp']*w_right,
            vmax=self.records[i_left]['vmax']*w_left + self.records[i_right]['vmax']*w_right,
            rmax=self.records[i_left]['rmax']*w_left + self.records[i_right]['rmax']*w_right,
            ustorm=self.records[i_left]['ustorm']*w_left + self.records[i_right]['ustorm']*w_right,
            vstorm=self.records[i_left]['vstorm']*w_left + self.records[i_right]['vstorm']*w_right
        )

        # now interpolate vinfo and radinfo
        # export np.nan if not available
        vinfo_left = self.records[i_left]['vinfo']
        lvinfo_left = len(vinfo_left)
        vinfo_right = self.records[i_right]['vinfo']
        lvinfo_right = len(vinfo_right)
        radinfo_left = np.atleast_2d(self.records[i_left]['radinfo'])
        sradinfo_left = radinfo_left.shape
        radinfo_right = np.atleast_2d(self.records[i_right]['radinfo'])
        sradinfo_right = radinfo_right.shape

        # Checking if the left and right are same size
        if lvinfo_left == lvinfo_right:
            vinfo_diff = False
        else:
            vinfo_diff = True

        # Interpolating
        if vinfo_diff:
            # vinfo size is different more check is needed
            min_vinfo_length = np.min([lvinfo_left, lvinfo_right])
            vinfo = vinfo_left[0:min_vinfo_length]

            # First find which one is the longer and set radinfo size
            if lvinfo_left > lvinfo_right:
                radinfo = np.zeros(shape=(min_vinfo_length, sradinfo_left[1]))
            elif lvinfo_left < lvinfo_right:
                radinfo = np.zeros(shape=(min_vinfo_length, sradinfo_right[1]))

            for i in np.arange(min_vinfo_length):
                    if np.any([np.isnan(vinfo_left[i]), np.isnan(vinfo_right[i])]):
                        radinfo = radinfo*np.nan
                    else:
                        vinfo[i] = vinfo_left[i]
                        for j in np.arange(radinfo.shape[1]):
                            radinfo[i, j] = radinfo_left[i, j]*w_left + radinfo_right[i, j]*w_right
        else:
            # vinfo size is same
            len_vinfo = lvinfo_left
            # If the both of them has length 1
            if len_vinfo == 1:
                # Return missing if vinfo itselft is missing
                if np.any([np.isnan(vinfo_left[0]), np.isnan(vinfo_right[0])]):
                    vinfo = np.nan
                    radinfo = np.nan
                # Or set to zero
                elif np.any([vinfo_left[0]==0, vinfo_right[0]==0]):
                    vinfo = np.nan
                    radinfo = np.nan
                # Otherwise calculate the linear interpolation
                else:
                    vinfo = vinfo_left[0]
                    radinfo = np.zeros_like(radinfo_left)
                    for j in np.arange(sradinfo_left[0]):
                        radinfo[j] = radinfo_left[j]*w_left + radinfo_right[j]*w_right
            elif len_vinfo > 1:
                # If both of them as length > 1
                vinfo = vinfo_left
                shape_radinfo = (lvinfo_left, sradinfo_left[1])
                radinfo = np.zeros(shape=shape_radinfo)
                for i, _ in enumerate(vinfo):
                    if np.any([np.isnan(vinfo_left[i]), np.isnan(vinfo_right[i])]):
                        radinfo = radinfo*np.nan
                    else:
                        vinfo[i] = vinfo_left[i]
                        for j in np.arange(shape_radinfo[1]):
                            radinfo[i, j] = radinfo_left[i, j]*w_left + radinfo_right[i, j]*w_right
        
        # Providing the same as the dataset if interpolated on a given time
        if w_right == 1:
            vinfo = vinfo_right
            radinfo = radinfo_right
        elif w_left == 1:
            vinfo = vinfo_left
            radinfo = radinfo_left

        # Updating int_record with vinfo, radinfo
        int_record['vinfo'] = vinfo
        int_record['radinfo'] = radinfo

        # Return the record file for rest of the calculations
        return(int_record)

    def plot(self, ax=None, subplot_kw={'projection':ccrs.PlateCarree()}):
        if not isinstance(ax, plt.Axes):
            _, ax = plt.subplots(subplot_kw=subplot_kw)
        else:
            ax = ax
        
        ax.plot(self.lon, self.lat, '.-')
        
        return(ax)

    def __str__(self):
        '''
        String representation for print function.
        '''
        out_str = '\n'.join(str(record) for record in self.records)
        return(out_str)

class Fields(object):
    def __init__(self, track, nwp):
        self.track = track
        self.nwp = nwp
    
    def uwind(self, at):
        raise NotImplementedError

    def vwind(self, at):
        raise NotImplementedError

    def pmsl(self, at):
        raise NotImplementedError

    def tempratature(self, at):
        raise NotImplementedError

    def humidity(self, at):
        raise NotImplementedError

def read_jtwc(fname):
    '''
    A reader function for reading JTWC file.

    The coded fields not found on the tracks are tagged as np.nan
    '''
    # Wind codes not implemented
    WINDCODE_NOTIMPLEMENTED = {
        'NNS' : 'north semicircle',
        'NES' : 'northeast semicircle',
        'EES' : 'east semicircle',
        'SES' : 'southeast semicircle',
        'SSS' : 'south semicircle',
        'SWS' : 'southwest semicircle',
        'WWS' : 'west semicircle',
        'NWS' : 'northwest semicirlce',
        'NNQ' : 'north north',
        'EEQ' : 'east east', 
        'SEQ' : 'south east', 
        'SSQ' : 'south south', 
        'SWQ' : 'south west', 
        'WWQ' : 'west west', 
        'NWQ' : 'north west'}

    # Possible wind code
    WINDCODE_IMPLEMENTED = {
        'AAA' : 'full circle',
        'NEQ' : 'north east'
    }

    # Dummy variable for storage
    track = {}

    with open(fname) as f:
        records = f.readlines()

    for record in records:
        fields = record.split(',')
        
        # BASIN - basin, e.g. WP, , SH, CP, EP, AL
        basin = fields[0].strip()
        
        # CY - annual cyclone number: 1 through 99
        ncyclone = int(fields[1].strip())
        
        # YYYYMMDDHH - Warning Date-Time-Group: 0000010100 through 9999123123
        # Previous cyclone may have 2 digit year
        timestamp = fields[2].strip()
        
        # TECHNUM - objective technique sorting number: 00 - 99
        technum = fields[3].strip()
        
        # TECH - acronym for each objective technique or CARQ or WRNG
        # BEST for best track.
        tech = fields[4].strip()
        
        # TAU - forecast period: -24 through 120 hours
        # 0 for best-track
        # negative taus used for CARQ and WRNG records.
        tau = int(fields[5].strip())
        
        # LatN/S - Latitude (tenths of degrees) for the DTG
        # 0 through 900, N/S is the hemispheric index.
        lat = fields[6].strip()
        if lat[-1] == 'N':
            lat = float(lat[0:-1])/10
        elif lat[-1] == 'S':
            lat = float(lat[0:-1])/10*-1
        
        # LonE/W - Longitude (tenths of degrees) for the DTG
        # 0 through 1800, E/W is the hemispheric index.
        lon = fields[7].strip()
        if lon[-1] == 'E':
            lon = float(lon[0:-1])/10
        elif lon[-1] == 'W':
            lon = float(lon[0:-1])/10*-1
        else:
            raise Exception(f'Unknown direction code {lon[-1]}!')
            
        # VMAX - Maximum sustained wind speed in knots: 0 through 300
        try:
            vmax = float(fields[8].strip())
        except:
            vmax = np.nan
        finally:
            vmax = knot2mps(vmax)
        
        # MSLP - Minimum sea level pressure, 1 through 1100 MB. (hpa)
        try:
            mslp = float(fields[9].strip())
        except:
            mslp = np.nan
        finally:
            mslp = hpa2pa(mslp)
        
        # TY - Level of tc development:
        #    TD - tropical depression,
        #    TS - tropical storm,
        #    TY - typhoon,
        #    ST - super typhoon,
        #    TC - tropical cyclone,
        #    HU - hurricane,
        #    SD - subtropical depression,
        #    SS - subtropical storm,
        #    EX - extratropical systems,
        #    MD - monsoon depression,
        #    IN - inland,
        #    DS - dissipating,
        #    LO - low,
        #    WV - tropical wave,
        #    ET - extrapolated,
        #    XX - unknown.
        try:
            ty = fields[10].strip()
        except:
            ty = 'XX'
        
        # RAD - Wind intensity (kts) for the radii defined in this record
        # Typically 35, 50, 65 or 100.
        # Also 34, 50, 64
        try:
            radv = float(fields[11].strip())
            if radv == 0:
                radv = np.nan
        except:
            radv = np.nan
        finally:
            radv = knot2mps(radv)
        
        # WINDCODE - Radius code
        #    AAA - full circle
        #    NNS - north semicircle
        #    NES - northeast semicircle
        #    EES - east semicircle
        #    SES - southeast semicircle
        #    SSS - south semicircle
        #    SWS - southwest semicircle
        #    WWS - west semicircle
        #    NWS - northwest semicirlce
        #    QQQ - quadrant (NNQ, NEQ, EEQ, SEQ, SSQ, SWQ, WWQ, NWQ)
        try:
            windcode = fields[12].strip()
        except:
            windcode = 'AAA'
        
        if windcode in WINDCODE_NOTIMPLEMENTED:
            raise Exception(f'Windcode {windcode} not implemented')
        
        # RAD1 - If full circle, radius of specified wind intensity
        # If semicircle or quadrant, radius of specified wind intensity of circle portion specified in radius code. 
        # 0 - 1200 nm.
        try:
            rad1 = float(fields[13].strip())
            if rad1 == 0:
                rad1 = np.nan
        except:
            rad1 = np.nan
        finally:
            rad1 = ntm2m(rad1)
        
        # RAD2 - If full circle this field not used
        # If semicicle, radius (nm) of specified wind intensity for semicircle not specified in radius code, 
        # If quadrant, radius (nm) of specified wind intensity for 2nd quadrant 
        # counting clockwise from quadrant specified in radius code
        # 0 through 1200 nm.
        try:
            rad2 = float(fields[14].strip())
            if rad2 == 0:
                rad2 = np.nan
        except:
            rad2 = np.nan
        finally:
            rad2 = ntm2m(rad2)
        
        # RAD3 - If full circle or semicircle this field not used
        # If quadrant, radius (nm) of specified wind intensity for 3rd quadrant
        # counting clockwise from quadrant specified in radius code
        # 0 through 1200 nm.
        try:
            rad3 = float(fields[15].strip())
            if rad3 == 0:
                rad3 = np.nan
        except:
            rad3 = np.nan
        finally:
            rad3 = ntm2m(rad3)
        
        # RAD4 - If full circle or semicircle this field not used
        # If quadrant, radius (nm) of specified wind intensity for 4th quadrant
        # counting clockwise from quadrant specified in radius code
        # 0 through 1200 nm.
        try:
            rad4 = float(fields[16].strip())
            if rad4 == 0:
                rad4 = np.nan
        except:
            rad4 = np.nan
        finally:
            rad4 = ntm2m(rad4)
        
        # Setting all the radius value to same for full circle
        if windcode == 'AAA':
            # if full circle
            rad2 = rad1
            rad3 = rad1
            rad4 = rad1
        
        # RADP - pressure in millibars of the last closed isobar, 900 - 1050 mb (hpa)
        try:
            pres = float(fields[17].strip())
        except:
            pres = np.nan
        finally:
            pres = hpa2pa(pres)
        
        # RRP - radius of the last closed isobar in nm, 0 - 9999 nm.
        try:
            rpres = float(fields[18].strip())
        except:
            rpres = np.nan
        finally:
            rpres = ntm2m(rpres)
        
        # MRD - radius of max winds, 0 - 999 nm.
        try:
            rmax = float(fields[19].strip())
        except:
            rmax = np.nan
        finally:
            rmax = ntm2m(rmax)
        
        # GUSTS - gusts, 0 through 995 kts.
        try:
            gusts = float(fields[20].strip())
        except:
            gusts = np.nan
        finally:
            gusts = knot2mps(gusts)
        
        # EYE - eye diameter, 0 through 999 nm.
        try:
            eye = float(fields[21].strip())
        except:
            eye = np.nan
        finally:
            eye = ntm2m(eye)
        
        # SUBREGN - subregion code: W, A, B, S, P, C, E, L.
        #    A - Arabian Sea
        #    B - Bay of Bengal
        #    C - Central Pacific
        #    E - Eastern Pacific
        #    L - Atlantic
        #    P - South Pacific (135E - 120W)
        #    S - South (20E - 135E)
        #    W - Western Pacific
        try:
            subregion = fields[22]
        except:
            subregion = None
        
        # MAXSEAS - max seas: 0 through 999 ft.
        try:
            maxseas = float(fields[23].strip())
        except:
            maxseas = np.nan
        finally:
            maxseas = ft2m(maxseas)
        
        # INITIALS - Forecaster's initials, used for tau 0 WRNG, up to 3 chars.
        try:
            initials = fields[24]
        except:
            initials = None
        
        # DIR - storm direction, 0 - 359 degrees.
        try:
            stormdir = float(fields[25].strip())
        except:
            stormdir = np.nan
        
        # SPEED - storm speed, 0 - 999 kts.
        try:
            stormspeed = float(fields[26].strip())
        except:
            stormspeed = np.nan
        finally:
            stormspeed = knot2mps(stormspeed)
        
        # STORMNAME - literal storm name, NONAME or INVEST
        # TCcyx used pre-1999
        #    where: cy = Annual cyclone number 01 through 99
        #            x = Subregion code: W, A, B, S, P, C, E, L.
        #                A - Arabian Sea
        #                B - Bay of Bengal
        #                C - Central Pacific
        #                E - Eastern Pacific
        #                L - Atlantic
        #                P - South Pacific (135E - 120W)
        #                S - South (20E - 135E)
        #                W - Western Pacific
        try:
            stormname = fields[27]
        except:
            stormname = None
        
        # DEPTH - system depth, D-deep, M-medium, S-shallow, X-unknown
        try:
            depth = fields[28]
        except:
            depth = None
        
        # SEAS - Wave height for radii defined in SEAS1-SEAS4, 0-99 ft.
        try:
            seas = float(fields[29])
        except:
            seas = np.nan
        finally:
            seas = ft2m(seas)
        
        # SEASCODE - Radius code:
        #    AAA - full circle
        #    NNS - north semicircle
        #    NES - northeast semicircle
        #    EES - east semicircle
        #    SES - southeast semicircle
        #    SSS - south semicircle
        #    SWS - southwest semicircle
        #    WWS - west semicircle
        #    NWS - northwest semicircle
        #    QQQ - quadrant (NNQ, NEQ, EEQ, SEQ, SSQ, SWQ, WWQ, NWQ)
        try:
            seacode = fields[30]
        except:
            seacode = 'AAA'
        
        # SEAS1 - first quadrant seas radius as defined by SEASCODE, 0 through 999 nm.
        try:
            seas1 = fields[31]
        except:
            seas1 = np.nan
        finally:
            seas1 = ntm2m(seas1)
        
        # SEAS2 - second quadrant seas radius as defined by SEASCODE, 0 through 999 nm.
        try:
            seas2 = fields[32]
        except:
            seas2 = np.nan
        finally:
            seas2 = ntm2m(seas2)
        
        # SEAS3 - third quadrant seas radius as defined by SEASCODE, 0 through 999 nm.
        try:
            seas3 = fields[33]
        except:
            seas3 = np.nan
        finally:
            seas3 = ntm2m(seas3)
        
        # SEAS4 - fourth quadrant seas radius as defined by SEASCODE, 0 through 999 nm.
        try:
            seas4 = fields[34]
        except:
            seas4 = np.nan
        finally:
            seas4 = ntm2m(seas4)
            
        if seacode == 'AAA':
            # Full circle
            seas2 = seas1
            seas3 = seas1
            seas4 = seas1
        
        if timestamp not in track:
            # new record
            vinfo = np.array([radv])
            radinfo = np.array([rad1, rad2, rad3, rad4])
            seainfo = np.array([seas1, seas2, seas3, seas4])
            track[timestamp] = {
                'basin':basin,
                'ncyclone':ncyclone,
                'technum':technum,
                'tech':tech,
                'tau':tau,
                'lon':lon, 
                'lat':lat, 
                'vmax':vmax,
                'ty':ty,
                'mslp':mslp,
                'pres':pres,
                'rpres':rpres,
                'gusts':gusts,
                'rmax':rmax,
                'eye':eye,
                'subregion':subregion,
                'maxseas':maxseas,
                'initials':initials,
                'stormdir':stormdir,
                'stormspeed':stormspeed,
                'stormname':stormname,
                'depth':depth,
                'seas':seas,
                'windcode':windcode,
                'vinfo': vinfo, 
                'radinfo': radinfo,
                'seacode':seacode,
                'seainfo':seainfo}
        else:
            if radv not in np.array(track[timestamp]['vinfo']):
                vinfo = np.array([radv])
                radinfo = np.atleast_2d([rad1, rad2, rad3, rad4])
                track[timestamp]['vinfo'] = np.append(track[timestamp]['vinfo'], vinfo)
                track[timestamp]['radinfo'] = np.vstack((track[timestamp]['radinfo'], radinfo))
            
            if seas not in np.array(track[timestamp]['seas']):
                seas = np.array([seas])
                seainfo = np.atleast_2d([seas1, seas2, seas3, seas4])
                track[timestamp]['seas'] = np.append(track[timestamp]['seas'], seas)
                track[timestamp]['seainfo'] = np.vstack((track[timestamp]['seainfo'], seainfo))

    # Create the track class
    records = np.array([])
    for record in track:
        record_obj = Record(
            timestamp = datetime.strptime(record, '%Y%m%d%H'),
            lon = track[record]['lon'],
            lat = track[record]['lat'],
            mslp = track[record]['mslp'],
            vmax = track[record]['vmax'],
            rmax = track[record]['rmax'],
            vinfo = track[record]['vinfo'],
            radinfo = track[record]['radinfo']
        )
        records = np.append(records, record_obj)

    return(Track(records=records))

if __name__=='__main__':
    print('Cyclone module of pycaz package.')