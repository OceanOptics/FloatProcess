# -*- coding: utf-8 -*-
# @Author: nils
# @Date:   2016-03-10 16:40:35
# @Last Modified by:   nils
# @Last Modified time: 2017-08-10 08:58:29

# DASHBOARD: update json files for web dashboard
#     float_list.json
#     float_status.json
#     google_map.json

try: import simplejson as json
except ImportError: import json
import os
import numpy as np
import sqlite3
from datetime import datetime
from collections import OrderedDict
from geojson import Feature, Point, LineString, FeatureCollection
from scipy.interpolate import interp1d

######################
#  DASHBOARD FIELDS  #
######################
# fields for profile
PROFILE_FIELDS = ['p','par','t','s','chla_adj','bbp','fdom','o2_c']
PROFILE_FIELDS_MANDATORY = ['p','t','s','chla_adj']
# fields for timeseries
TIMESERIES_FIELDS = ['profile_id', 'dt','mld','t','s','chla_adj','bbp','fdom','o2_c']
TIMESERIES_FIELDS_MANDATORY = ['profile_id', 'dt','mld','t','s', 'chla_adj']
# fields for contour plot
CONTOUR_PLOT_FIELDS = ['par','t','s','chla_adj','bbp','fdom','o2_c']
CONTOUR_PLOT_FIELDS_MANDATORY = ['t', 'chla_adj']
# fiels for engineering data
ENGINEERING_DATA_FIELDS = ['AirPumpAmps', 'AirPumpVolts',
                           'BuoyancyPumpAmps', 'BuoyancyPumpVolts',
                           'QuiescentAmps', 'QuiescentVolts',
                           'Sbe41cpAmps', 'Sbe41cpVolts',
                           'McomsAmps', 'McomsVolts',
                           'Sbe63Amps', 'Sbe63Volts']

FIELD_NAME = {'p':'Pressure', 'par':'PAR', 't':'Temperature', 's':'Salinity',
              'chla_adj':'Chlorophyll a', 'bbp':'bbp', 'fdom':'FDOM', 'o2_c':'O2'}
FIELD_LABEL = {'p':'Pressure (dBar)', 'par':'PAR (umol photons m<sup>-2</sup> s<sup>-1</sup>)',
               't':'Temperature (&deg;C)', 's':'Salinity (ppt)',
               'chla_adj':'Chlorophyll <i>a</i> (mg m<sup>-3</sup>)',
               'bbp':'b<sub>bp</sub>(700) (m<sup>-1</sup>)',
               'fdom':'FDOM (mg m<sup>-3</sup>)',
               'o2_c':'O<sub>2</sub> (mg m<sup>-3</sup>)'}
FIELD_COLOR_SCALE = {'par':'YIGnBu', 't':'RdBu', 's':'YIGnBu', 'chla_adj':'Greens', 'bbp':'Jet', 'fdom':'Portland', 'o2_c':'YIGnBu'}
FIELD_REVERSE_SCALE = {'par':False, 't':False, 's':False, 'chla_adj':True, 'bbp':False, 'fdom':False, 'o2_c':False}
FIELD_PRECISION = {'par':'.2f', 't':'.2f', 's':'.4f', 'chla_adj':'.3f', 'bbp':'.5f', 'fdom':'.3f', 'o2_c':'.2f'}

def update_float_status(_filename, _float_id, _wmo='undefined',
                        _profile_n=-1, _dt_last='undefined',
                        _dt_first='undefined', _status='undefined',
                        _institution='undefined', _project='undefined',
                        _reset=False):
    # UPDATE_FLOAT_STATUS: update json file of float status
    # EXAMPLE:
    #   update_float_status('float_status.json', 'n0572', _wmo='5902462',
    #     _dt_last=datetime.today())
    # DEPRECATED

    # load current float status
    if os.path.isfile(_filename) and not _reset:
        with open(_filename) as data_file:
            fs = json.load(data_file, object_pairs_hook=OrderedDict)
        if _float_id not in fs.keys():
            fs[_float_id] = dict()
            fs[_float_id]['float_id'] = _float_id
    else:
        fs = OrderedDict()
        fs[_float_id] = dict()

    # set date of update in zulu time
    dt_update = datetime.utcnow()
    fs[_float_id]['dt_update'] = dt_update.strftime('%d-%b-%Y %H:%M:%S')
    # update wmo
    if _wmo != 'undefined':
        fs[_float_id]['wmo'] = _wmo
    # update profile number
    if _profile_n != -1:
        fs[_float_id]['profile_n'] = _profile_n
    # update institution
    if _institution != 'undefined':
        fs[_float_id]['institution'] = _institution
    # update project
    if _project != 'undefined':
        fs[_float_id]['project'] = _project
    # update date of last report
    if _dt_last != 'undefined':
        fs[_float_id]['dt_last'] = _dt_last.strftime('%d-%b-%Y %H:%M:%S')
        dt_last = _dt_last
    else:
        dt_last = datetime.strptime(
            fs[_float_id]['dt_last'], '%d-%b-%Y %H:%M:%S')
    # update days since last report
    delta_last = dt_update - dt_last
    fs[_float_id]['days_last'] = delta_last.days
    # update date of first report
    if _dt_first != 'undefined':
        fs[_float_id]['dt_first'] = _dt_first.strftime('%d-%b-%Y %H:%M:%S')
    elif ('dt_first' not in fs[_float_id].keys() or
          fs[_float_id]['dt_first'] == 'undefined') and _profile_n == 0:
        fs[_float_id]['dt_first'] = dt_last.strftime('%d-%b-%Y %H:%M:%S')
    # update days since first report
    if 'dt_first' in fs[_float_id].keys():
        dt_first = datetime.strptime(
            fs[_float_id]['dt_first'], '%d-%b-%Y %H:%M:%S')
        delta_first = dt_update - dt_first
        fs[_float_id]['days_first'] = delta_first.days
    # update float status
    if _status != 'undefined':
        fs[_float_id]['status'] = _status
    elif delta_last.days > 15:
        fs[_float_id]['status'] = 'inactive'
    else:
        fs[_float_id]['status'] = 'active'

    with open(_filename, 'w') as outfile:
        json.dump(fs, outfile)


def update_db(_msg, _usr_cfg, _app_cfg):
    # Update database
    #
    #
    # INPUT:
    #   _msg dictionnary containing float profile
    #   _usr_cfg <dictionnary> float configuration
    #   _app_cfg <dictionnary> application configuration
    #
    # OUTPUT:
    #   update metadata in SQLite3 database
    #       path to database:
    #   0 if exporation went well
    #     or
    #   -1 if error during exportation process

    # Connect to database
    db = sqlite3.connect(_app_cfg['dashboard']['path']['db'])

    # Check if first profile
    if _msg['profile_id'] == 0:
        dt_deploy = _msg['dt']
        lat_deploy = _msg['lat']
        lon_deploy = _msg['lon']
    else:
        dt_deploy = ''
        lat_deploy = -9999
        lon_deploy = -9999

    # Check if float in db
    cur = db.execute('SELECT id FROM meta WHERE wmo = ?', [_usr_cfg['wmo']])
    entries = cur.fetchall()
    if not entries:
        # New float metadata
        db.execute('INSERT INTO meta (wmo, lab_id, pi, project, model,'
                                      'profile,'
                                      'dt_deploy, lat_deploy, lon_deploy,'
                                      'dt_report, lat_report, lon_report,'
                                      'status)'
                                      ' VALUES'
                                      ' (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    [int(_usr_cfg['wmo']), _usr_cfg['user_id'], _usr_cfg['pi'],
                     _usr_cfg['project'],_usr_cfg['model'],
                     _msg['profile_id'], dt_deploy,lat_deploy,lon_deploy,
                     _msg['dt'], _msg['lat'], _msg['lon'],
                     'NA'])
    else:
        # Display warning
        if len(entries) > 1:
            print('WARNING: Float is present more than once in db')
        # Update float metadata
        if dt_deploy == '':
            db.execute('UPDATE meta SET wmo = ?, lab_id = ?, pi = ?, project = ?,'
                                        'model = ?, profile = ?,'
                                        'dt_report = ?, lat_report = ?, lon_report = ?,'
                                        'status = ?'
                                        'WHERE id = ?',
                        [int(_usr_cfg['wmo']), _usr_cfg['user_id'], _usr_cfg['pi'],
                         _usr_cfg['project'], _usr_cfg['model'],
                         _msg['profile_id'],
                         _msg['dt'], _msg['lat'], _msg['lon'],
                         'NA', entries[0][0]])
        else:
            db.execute('UPDATE meta SET wmo = ?, lab_id = ?, pi = ?, project = ?,'
                                        'model = ?, profile = ?,'
                                        'dt_deploy = ?, lat_deploy = ?, lon_deploy = ?,'
                                        'dt_report = ?, lat_report = ?, lon_report = ?,'
                                        'status = ?'
                                        'WHERE id = ?',
                        [int(_usr_cfg['wmo']), _usr_cfg['user_id'], _usr_cfg['pi'],
                         _usr_cfg['project'], _usr_cfg['model'],
                         _msg['profile_id'], dt_deploy, lat_deploy, lon_deploy,
                         _msg['dt'], _msg['lat'], _msg['lon'],
                         'NA', entries[0][0]])
    # Add float engineering data
    if set(ENGINEERING_DATA_FIELDS).issubset(_msg.keys()):
        db.execute('INSERT INTO engineering_data (lab_id, profile_id, dt,'
                                                 'AirPumpAmps, AirPumpVolts,'
                                                 'BuoyancyPumpAmps, BuoyancyPumpVolts,'
                                                 'QuiescentAmps, QuiescentVolts,'
                                                 'Sbe41cpAmps, Sbe41cpVolts,'
                                                 'McomsAmps, McomsVolts,'
                                                 'Sbe63Amps, Sbe63Volts) VALUES '
                                                 '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    [_usr_cfg['user_id'], _msg['profile_id'], _msg['dt'],
                    _msg['AirPumpAmps'], _msg['AirPumpVolts'],
                    _msg['BuoyancyPumpAmps'], _msg['BuoyancyPumpVolts'],
                    _msg['QuiescentAmps'], _msg['QuiescentVolts'],
                    _msg['Sbe41cpAmps'], _msg['Sbe41cpVolts'],
                    _msg['McomsAmps'], _msg['McomsVolts'],
                    _msg['Sbe63Amps'], _msg['Sbe63Volts']])
    db.commit()

    # Disconnect from database
    db.close()


def export_msg_to_json_profile(_msg, _path, _usr_id):
    # Profile of each cast for all variables
    #   p
    #   par
    #   temperature
    #   salinity
    #   chla
    #   poc
    #   fdom
    #   o2


    # Check input
    if 'obs' not in _msg.keys():
        print('ERROR: Missing key obs in msg.')
        return -1
    # Set filename
    filename = os.path.join(_path, _usr_id + '.' +
                            '{0:03d}'.format(_msg['profile_id']) +
                            '.profile.json')
    # Set precision
    json.encoder.FLOAT_REPR = lambda o: format(o, '.5f')
    # Extract data
    fs = dict()
    for f in PROFILE_FIELDS:
        if f not in _msg['obs'].keys():
            if f in PROFILE_FIELDS_MANDATORY:
                print('ERROR: Missing key ' + f + ' in msg[obs].')
                return -1
            else:
                continue
        # Convert np.array to list
        if isinstance(_msg['obs'][f], np.ndarray):
            fs[f] = _msg['obs'][f].tolist()
        else:
            fs[f] = _msg['obs'][f]

    # Write json
    with open(filename, 'w') as outfile:
        json.dump(fs, outfile, ignore_nan=True,default=datetime.isoformat)
        return 0
    return -1

def export_msg_to_json_timeseries(_msg, _path, _usr_id, _reset=False):
    # Compute time series within MLD of TIMESERIES_FIELDS
    #   for each parameter return median, 5 and 95 percentile.

    # Check input
    if 'obs' not in _msg.keys():
        print('ERROR: Missing key obs in msg.')
        return -1
    if 'mld_index' not in _msg.keys():
        print('ERROR: Missing key mld_index in msg ' + '{0:03d}'.format(_msg['profile_id'])  + '.')
        return -1
    # Set filename
    filename = os.path.join(_path, _usr_id + '.timeseries.json')
    # Set precision
    json.encoder.FLOAT_REPR = lambda o: format(o, '.5f')
    # Load existing timeseries (if available)
    if os.path.isfile(filename) and not _reset:
        with open(filename) as data_file:
            fs = json.load(data_file)
    else:
        fs = dict()
        for f in TIMESERIES_FIELDS:
            fs[f] = list()
            fs[f + '_prtl5'] = list()
            fs[f + '_prtl95'] = list()

    # Get selection above MLD
    if 'mld' in _msg.keys():
        mld = _msg['mld']
    else:
        print('ERROR: Missing key mld in msg.')
        return -1
    if 'p' in _msg['obs'].keys():
        p = _msg['obs']['p']
    else:
        print('ERROR: Missing key p in msg[obs].')
        return -1
    sel = p <= mld
    # If no values above the MLD, compute for shallowest value
    if not any(sel):
        i = np.argmin(p)
        sel[i] = True
        print('WARNING: No depth above MLD, using p=%.2f' % p[i])
    # Extract data
    for f in TIMESERIES_FIELDS:
        if f in _msg.keys():
            # field with one value
            fs[f].append(_msg[f])
        elif f in _msg['obs'].keys():
            # average in MLD
            fs[f].append(np.nanmedian(_msg['obs'][f][sel]))
            fs[f+'_prtl5'].append(np.percentile(_msg['obs'][f][sel], 5))
            fs[f+'_prtl95'].append(np.percentile(_msg['obs'][f][sel], 95))
        elif f in TIMESERIES_FIELDS_MANDATORY:
            print('ERROR: Missing key ' + f + ' in msg|msg[obs].')
            return -1
        else:
            fs[f].append(np.NaN)

    # TODO Remove duplicates and sort data by profile id

    # Write json
    with open(filename, 'w') as outfile:
        json.dump(fs, outfile, ignore_nan=True,default=datetime.isoformat)
        return 0
    return -1

def export_msg_to_json_contour_plot(_msg, _path, _usr_id, _reset=False):
    # Open current contour_plot file of each variable and add current profile
    # Used to generate contour plot x: time; y: pressure; c: observation
    #
    # TODO Dynamic depth range (250, 500, 1000, 1500, 2000), currently fix

    # Check input
    if 'obs' not in _msg.keys():
        print('ERROR: Missing key obs in msg.')
        return -1

    # For each variable
    for f in CONTOUR_PLOT_FIELDS:
        if f in _msg['obs'].keys():
            # Set filename
            filename = os.path.join(_path, _usr_id + '.' + f + '.contour.json')

            # Load existing contour plot (if available)
            if os.path.isfile(filename) and not _reset:
                with open(filename) as data_file:
                    fs = json.load(data_file)
            else:
                fs = dict('')
                fs['name'] = FIELD_NAME[f]
                fs['label'] = FIELD_LABEL[f]
                fs['colorscale'] = FIELD_COLOR_SCALE[f]
                fs['reversescale'] = FIELD_REVERSE_SCALE[f]
                fs['dt'] = list()
                # set p according to deepest point of first profile
                if f == 'par':
                    fs['p'] = list(range(0,251,2))
                else:
                    fs['p'] = list(range(0,1001,2)) 
                fs['mld'] = list()
                # set a 2d array with numpy
                fs['data'] = list(list() for i in range(len(fs['p'])))

            # Update dt
            fs['dt'].append(_msg['dt'])

            # Update MLD
            fs['mld'].append(_msg['mld'])

            # Interpolate profile on p grid
            npv = np.array(_msg['obs'][f])
            sel = np.logical_not(np.isnan(_msg['obs'][f]))
            if np.sum(sel) > 2:
                # Interpolate with nearest value (keep intensity of spikes)
                fun = interp1d(_msg['obs']['p'][sel], npv[sel], kind='nearest',
                           bounds_error=False, fill_value=np.NaN)
                var_interp = fun(fs['p'])
            else:
                print('WARNING: Unable to consolidate ' + str(_msg['float_id']) + '.' + str(_msg['profile_id']) + '.' + f)
                var_interp = np.full(len(_msg['obs']['p']), np.nan)

            # Update data matrix
            for i in range(len(var_interp)):
                fs['data'][i].append(var_interp[i])

            # Set precision
            json.encoder.FLOAT_REPR = lambda o: format(o, FIELD_PRECISION[f])

            # Write json profile
            with open(filename, 'w') as outfile:
                json.dump(fs, outfile, ignore_nan=True,default=datetime.isoformat)
        elif f in CONTOUR_PLOT_FIELDS_MANDATORY:
            print('ERROR: Missing key ' + f + ' in msg|msg[obs].')
            return -1
    return  0

def export_msg_to_json_map(_msg, _path, _usr_id, _reset=False):
    # Open current geojson file, add input parameters

    # Set filename
    filename = os.path.join(_path, _usr_id + '.geo.json')
    # Set precision
    json.encoder.FLOAT_REPR = lambda o: format(o, '.3f')
    # Load previous positions
    if os.path.isfile(filename) and not _reset:
        with open(filename) as data_file:
            fc = json.load(data_file)
            all_pos = []
            # Read previous position from LineString
            for f in fc['features']:
                if (f['geometry']['type'] == 'LineString' and
                    f['properties']['usr_id'] == _usr_id):
                    all_pos = f['geometry']['coordinates']
                    break
            # If no previous position found in LineString
            if not all_pos:
                # Read previous position from Point
                for f in fc['features']:
                    if (f['geometry']['type'] == 'Point' and
                        f['properties']['usr_id'] == _usr_id):
                        all_pos = [f['geometry']['coordinates']]
                        break
    else:
        all_pos = []

    # Make Point feature for last position
    pos = (_msg['lon'], _msg['lat'])
    feature_last_position = Feature(geometry=Point(pos),
                            properties={'usr_id': _usr_id,
                                        'msg_id': _msg['profile_id'],
                                        'dt': _msg['dt']})

    # Make LineString feature if more than one position
    if not all_pos:
        feature_collection = FeatureCollection([feature_last_position])
    else:
        all_pos.append(pos)
        feature_all_positions = Feature(geometry=LineString(all_pos),
                                properties={'usr_id': _usr_id})
        feature_collection = FeatureCollection([feature_last_position,
                                                feature_all_positions])

    # Write json
    with open(filename, 'w') as outfile:
        json.dump(feature_collection, outfile,
                        ignore_nan=True, default=datetime.isoformat)
        return 0
    return -1

if __name__ == '__main__':
    from process import bash
    # bash(['n0572', 'n0573', 'n0574', 'n0646', 'n0647', 'n0648'])
    bash(['metbio003d', 'metbio010d'])

