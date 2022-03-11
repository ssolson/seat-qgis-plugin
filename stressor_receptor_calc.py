# -*- coding: utf-8 -*-
"""
/***************************************************************************
 StressorReceptorCalc
                                 A QGIS plugin
 This calculates a response layer from stressor and receptor layers
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2021-04-19
        git sha              : $Format:%H$
        copyright            : (C) 2021 by Integral Consultsing
        email                : ependleton@integral-corp.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QTableWidgetItem, QGridLayout
from qgis.core import QgsProject, Qgis, QgsApplication, QgsVectorLayer, QgsMessageLog, QgsRasterLayer, QgsRasterBandStats, QgsCoordinateReferenceSystem
from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
from qgis.gui import QgsLayerTreeView, QgsProjectionSelectionDialog

from PyQt5.QtCore import Qt

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .stressor_receptor_calc_dialog import StressorReceptorCalcDialog
# import QGIS processing
import processing
import os.path
import csv, glob
import numpy as np
from osgeo import gdal
import pandas as pd
import shutil
import tempfile
import configparser
import xml.etree.ElementTree as ET
from netCDF4 import Dataset

# import netcdf calculations
from .readnetcdf_createraster import transform_netcdf_ro, create_raster, numpy_array_to_raster
# UTM finder
from .Find_UTM_srid import find_utm_srid

# grab the data time
from datetime import date
import logging

def df_from_qml(fpath):
    tree = ET.parse(fpath)
    root = tree.getroot()

    v = [i.get('label') for i in root[3][1][2][0].findall('item')]
    v2 = [s.split(" - ") for s in v]
    df = pd.DataFrame(v2, columns = ['min', 'max'])
    if df.empty:
        # grab the values in a unique palette
        v1 = [i.get('value') for i in root[3][1][2].findall('paletteEntry')]
        v2 = [i.get('label') for i in root[3][1][2].findall('paletteEntry')]
        df = pd.DataFrame({'value':v1, 'label':v2})
    return df
    
class StressorReceptorCalc:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'StressorReceptorCalc_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Stressor Receptor Calculator')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('StressorReceptorCalc', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/stressor_receptor_calc/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Calculate a response layer from stressor and receptor layers'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Stressor Receptor Calculator'),
                action)
            self.iface.removeToolBarIcon(action)
    
    def select_calc_type(self, fields):
        '''This loads in any inputs into a drop down selector '''
        calcname=self.dlg.comboBox.currentIndex()
        # set up table
        path = os.path.join(QgsApplication.qgisSettingsDirPath(),
        r"python\plugins\stressor_receptor_calc\inputs", fields[calcname] + ".csv")
        path = path.replace(os.sep, '/')
        self.loadcsv(path)
        
    
    def loadcsv(self, filename):
        with open(filename) as csvfile:
            data = csv.reader(csvfile)
            col = next(data)
            ncol = len(col)
            nrow = sum([1 for row in data])
            # move to first row of data
            csvfile.seek(0)
            next(data)
            self.dlg.tableWidget.setColumnCount(ncol)
            self.dlg.tableWidget.setRowCount(nrow)
            #grid = QGridLayout()
            #grid.addWidget(self.dlg.tableWidget, nrow, ncol);
            self.dlg.tableWidget.setHorizontalHeaderLabels(col)
            for i, row in enumerate(data):
                for j, item in enumerate(row):
                    self.dlg.tableWidget.setItem(i,j, QTableWidgetItem(item))
            
            self.dlg.tableWidget.resizeColumnsToContents()
    """
    Deprecationed with transform NetCDF
    def select_receptor_file(self):
        # input the receptor file
        filename, _filter = QFileDialog.getOpenFileName(
        self.dlg, "Select Receptor","", '*.tif')
        self.dlg.lineEdit.setText(filename)
    """
    def select_device_file(self, presence):
        """ input the .nc file """
        filename, _filter = QFileDialog.getOpenFileName(
        self.dlg, "Select NetCDF file","", "*.tif; *.nc; *.ini")
        if presence  == 'not present':
            self.dlg.device_not_present.setText(filename)
        else:
            self.dlg.device_present.setText(filename)

    def select_bc_file(self):
        """ input the bc file """
        filename, _filter = QFileDialog.getOpenFileName(
        self.dlg, "Select Boundary Condition","", '*.csv')
        self.dlg.bc_prob.setText(filename)
    
    def select_run_order_file(self):
        """ input the bc file """
        filename, _filter = QFileDialog.getOpenFileName(
        self.dlg, "Select Run Order","", '*.csv')
        self.dlg.run_order.setText(filename)
        
    def select_crs(self):
        # input the crs
        
        projSelector = QgsProjectionSelectionDialog(None)
        # set up a default one
        crs = QgsCoordinateReferenceSystem()
        crs.createFromId(4326)
        projSelector.setCrs( crs )
        projSelector.exec()
        # projSelector.exec_()
        self.dlg.crs.setText(projSelector.crs().authid().split(":")[1])

    def select_receptor_file(self):
        # input the receptor file
        filename, _filter = QFileDialog.getOpenFileName(
        self.dlg, "Select Receptor","", '*.tif')
        self.dlg.receptor_file.setText(filename)
        
    def select_secondary_constraint_file(self):
        filename, _filter = QFileDialog.getOpenFileName(
        self.dlg, "Select Secondary Constraint","", '*.tif')
        self.dlg.sc_file.setText(filename)
    
    def select_output_file(self):
        filename, _filter = QFileDialog.getSaveFileName(
        self.dlg, "Select Output","", '*.tif')
        self.dlg.ofile.setText(filename)
    
    def calculate_stressor(self, dev_present_file, dev_notpresent_file, bc_file, run_order_file, svar, crs, output_path, output_path_reclass, receptor_filename):
        
        # configuration for raster translate
        GDAL_DATA_TYPE = gdal.GDT_Float32 
        GEOTIFF_DRIVER_NAME = r'GTiff'
                
        # all runs
        # bcarray = [i for i in range(1,23)]
        
        # Skip the bad runs for now
        # bcarray = np.array([0,1,2,3,4,5,6,7,9,10,11,12,13,14,15,16,17,19,20,22])
        
        #SWAN will always be in meters. Not always WGS84
        
        # in the netcdf file maybe?
        SPATIAL_REFERENCE_SYSTEM_WKID = crs #WGS84 meters
        nbands = 1
        # bottom left, x, y netcdf file
        # bounds = [-124.2843933,44.6705] #x,y or lon,lat, this is pulled from an input data source
        # look for dx/dy
        #cell_resolution = [0.0008,0.001 ] #x res, y res or lon, lat, same as above
        
        # from Kaus -235.8+360 degrees = 124.2 degrees. The 235.8 degree conventions follows longitudes that increase 
        # eastward from Greenwich around the globe. The 124.2W, or -124.2 goes from 0 to 180 degrees to the east of Greenwich.
        file = Dataset(dev_present_file)
        xcor = file.variables['XCOR'][:].data
        ycor = file.variables['YCOR'][:].data
        
        #bounds = [xcor.min() - 360,ycor.min()] #x,y or lon,lat, this is pulled from an input data source
        # adjusted to match original
        # bounds = [xcor.min() - 360 - 0.000396717968754956,ycor.min() + 0.19050045776366886]
        bounds = [xcor.min() - 360, ycor.min()]
        #bounds = [round(bounds[0], 4), round(bounds[1], 4)]
    
        # look for dx/dy
        dx = xcor[1,0] - xcor[0,0]
        dy = ycor[0,1] - ycor[0,0]
        cell_resolution = [dx,dy ]
        
        # original
        # if not a Geotiff
        #if '.tif' not in dev_present_file:
        # original
        # rows, cols, numpy_array = transform_netcdf(dev_present_file, dev_notpresent_file, bc_file, run_order_file, bcarray, svar)
        # new bc one
        rows, cols, numpy_array = transform_netcdf_ro(dev_present_file, dev_notpresent_file, bc_file, run_order_file, svar,receptor_filename = receptor_filename)
        #if '.tif' in dev_present_file:
        #    rows, cols, numpy_array = read_raster_calculate_diff(dev_present_file, dev_notpresent_file)
        
        # create an ouput raster given the stressor file path
        output_raster = create_raster(output_path,
                          cols,
                          rows,
                          nbands)
     
        # post processing of numpy array to output raster
        
        output_raster = numpy_array_to_raster(output_raster,
                                  numpy_array,
                                  bounds,
                                  cell_resolution,
                                  SPATIAL_REFERENCE_SYSTEM_WKID, output_path)
                                  
        # create an ouput raster given the reclassified stressor file path
        output_raster_reclass = create_raster(output_path_reclass,
                          cols,
                          rows,
                          nbands)
        
        # reclassify according to the break value
        numpy_array_reclass = numpy_array.copy()
        
        # deprecated for now. Make zeros NA
        # numpy_array_reclass[numpy_array<=reclass_breakval] = 1
        # numpy_array_reclass[numpy_array>reclass_breakval] = 0
        
        # make null
        # numpy_array_reclass[numpy_array == 0] = np.nan
       
        # post processing of numpy array to output raster
        output_raster_reclass = numpy_array_to_raster(output_raster_reclass,
                                  numpy_array_reclass,
                                  bounds,
                                  cell_resolution,
                                  SPATIAL_REFERENCE_SYSTEM_WKID, output_path_reclass)                         
        
        return output_path, output_path_reclass
        
    def raster_multi(self, r, s, sc, opath):
        ''' Raster multiplication '''
        #rLayer  = QgsRasterLayer(r, "r")
        #tLayer  = QgsRasterLayer(t, "t")
        
        #entries = []
        rbasename = os.path.splitext(os.path.basename(r))[0]
        #Define receptor
        # rl = QgsRasterCalculatorEntry()
        # rl.ref = 'r@1'
        # rl.raster = rLayer
        # rl.bandNumber = 1
        # entries.append( rl )
        
        #Define stressor
        sbasename = os.path.splitext(os.path.basename(s))[0]
        
        # Define constraint
        if not sc == "":
            scbasename = os.path.splitext(os.path.basename(sc))[0]
            # scl = QgsRasterCalculatorEntry()
            # scl.ref = 'sc@1'
            # scl.raster = scLayer
            # scl.bandNumber = 1
            # entries.append(scl)
        
        # grab the current transform to avoid deprecation warnings
        #coordinateTransformContext=QgsProject.instance().transformContext()
        
        if sc == "":
            params = { 'CELLSIZE' : None, 'CRS' : None, 'EXPRESSION' : '\"' + rbasename + '@1\" * \"' + sbasename + '@1\"', 
            'EXTENT' : None, 'LAYERS' : [r, s], 
            'OUTPUT' : opath}
        else:
            params = { 'CELLSIZE' : None, 'CRS' : None, 'EXPRESSION' : '\"' + rbasename + '@1\" * \"' + sbasename + '@1\" * \"' + scbasename + '@1\"', 
            'EXTENT' : None, 'LAYERS' : [r, s, sc], 
            'OUTPUT' : opath}

        processing.run("qgis:rastercalculator", params)
        
    def raster_add(self, rfiles, opath):
    
        ''' Raster addition '''

        nbase = [os.path.splitext(os.path.basename(rfile))[0] for rfile in rfiles]

        params = { 'CELLSIZE' : None, 'CRS' : None, 'EXPRESSION' : '@1 + '.join(nbase) +'@1', 
        'EXTENT' : None, 'LAYERS' : rfiles, 
        'OUTPUT' : opath}

        processing.run("qgis:rastercalculator", params)
        
        return opath    
    
    def raster_subtract(self, cec, no_cec, opath, prob = 1):
    
        ''' Raster subtraction '''
        layers = [cec, no_cec]
        cecbasename = os.path.splitext(os.path.basename(cec))[0]
        
        #Define stressor
        no_cecbasename = os.path.splitext(os.path.basename(no_cec))[0]
        """
        params = { 'CELLSIZE' : None, 'CRS' : None, 'EXPRESSION' : '\"' + cecbasename + '@1\" - "' + no_cecbasename + '@1\"', 
            'EXTENT' : None, 'LAYERS' : [cec, no_cec], 
            'OUTPUT' : opath}

        processing.run("qgis:rastercalculator", params)
        """
        # "@1 + ".join(colors) + '@1'
        params = { 'CELLSIZE' : None, 'CRS' : None, 'EXPRESSION' : '({0}@1 - {1}@1) * {2}'.format(cecbasename, no_cecbasename, prob), 
        'EXTENT' : None, 'LAYERS' : layers, 
        'OUTPUT' : opath}

        processing.run("qgis:rastercalculator", params)
        
        return opath
    
    def raster_subtract_d50(self, cec, no_cec, tcrit, opath, prob = 1):
    
        ''' Raster subtraction '''
        layers = [cec, no_cec, tcrit]
        cecbasename = os.path.splitext(os.path.basename(cec))[0]
        
        #Define stressor
        no_cecbasename = os.path.splitext(os.path.basename(no_cec))[0]
        """
        params = { 'CELLSIZE' : None, 'CRS' : None, 'EXPRESSION' : '\"' + cecbasename + '@1\" - "' + no_cecbasename + '@1\"', 
            'EXTENT' : None, 'LAYERS' : [cec, no_cec], 
            'OUTPUT' : opath}

        processing.run("qgis:rastercalculator", params)
        """
        # "@1 + ".join(colors) + '@1'
        params = { 'CELLSIZE' : None, 'CRS' : None, 'EXPRESSION' : '(({0}@1 - {1}@1) * {2}) / {3}/ 10)'.format(cecbasename, no_cecbasename, prob, tcrit), 
        'EXTENT' : None, 'LAYERS' : layers, 
        'OUTPUT' : opath}

        processing.run("qgis:rastercalculator", params)
        
        return opath
    
        
    def style_layer(self, fpath, stylepath, checked = True, ranges = True):
        # add the result layer to map
        basename = os.path.splitext(os.path.basename(fpath))[0]
        layer = QgsProject.instance().addMapLayer(QgsRasterLayer(fpath, basename))
        
        if stylepath != "":
            # apply layer style
            layer.loadNamedStyle(stylepath)

            # reload to see layer classification
            layer.reload()
        
        # refresh legend entries
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())
        
        if not checked:
            root = QgsProject.instance().layerTreeRoot()
            root.findLayer(layer.id()).setItemVisibilityChecked(checked)
        if ranges:
            range = [x[0] for x in layer.legendSymbologyItems()]
            return range
    
    def export_area(self, ofilename, crs, ostylefile = None):
        cfile = ofilename.replace('.tif', '.csv')
        if os.path.isfile(cfile):
            os.remove(cfile)
                
        if ostylefile is not None:
            sdf = df_from_qml(ostylefile)
        
        
        basename = os.path.splitext(os.path.basename(ofilename))[0]
        raster = QgsProject.instance().mapLayersByName(basename)[0]
        
        xmin = raster.extent().xMinimum()
        xmax = raster.extent().xMaximum()
        ymin = raster.extent().yMinimum()
        ymax = raster.extent().yMaximum()
        
        assert find_utm_srid(xmin, ymin, crs) == find_utm_srid(xmax, ymax, crs), 'grid spans multiple utms'
        crs_found = find_utm_srid(xmin, ymin, crs)
        
        outfile = tempfile.NamedTemporaryFile(suffix='.tif').name
        #cmd = f'gdalwarp -s_srs EPSG:{crs} -t_srs EPSG:{crs_found} -r near -of GTiff {ofilename} {outfile}'
        #os.system(cmd)
        
        reproject_params = {'INPUT':ofilename,
                'SOURCE_CRS':QgsCoordinateReferenceSystem(f'EPSG:{crs}'),
                'TARGET_CRS':QgsCoordinateReferenceSystem(f'EPSG:{crs_found}'),
                'RESAMPLING':0,
                'NODATA':None,
                'TARGET_RESOLUTION':None,
                'OPTIONS':'',
                'DATA_TYPE':0,
                'TARGET_EXTENT':None,
                'TARGET_EXTENT_CRS':QgsCoordinateReferenceSystem(f'EPSG:{crs_found}'),
                'MULTITHREADING':False,
                'EXTRA':'',
                'OUTPUT':outfile}

        processing.run("gdal:warpreproject", reproject_params)
        
        
        params = { 'BAND' : 1, 
        'INPUT' : outfile, 
        'OUTPUT_TABLE' : cfile }
        
        processing.run("native:rasterlayeruniquevaluesreport", params)
        
        os.remove(outfile)
        
        
        df = pd.read_csv(cfile, encoding = 'cp1252')
        df.rename(columns = {'m²':'m2'}, inplace = True)
        df = df.groupby(by = ['value']).sum().reset_index()
        
        df['percentage'] = (df['m2'] / df['m2'].sum()) * 100.
   
        df['value'] = df['value'].astype(float)
        # recode 0 to np.nan
        df.loc[df['value'] == 0, 'value'] = float('nan')
        
        df = df.sort_values(by = ['value'])
        
        
        if ostylefile is not None:
            df = pd.merge(df, sdf, how = 'left', on = 'value')
            df.loc[:, ['value','label', 'count', 'm2', 'percentage']].to_csv(cfile, index = False)
        else:
            df.loc[:, ['value', 'count', 'm2', 'percentage']].to_csv(cfile, na_rep='NULL', index = False)
        
    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False
            self.dlg = StressorReceptorCalcDialog()
            # this set the plugin to be the top most window
            # self.dlg.setWindowFlags(Qt.WindowStaysOnTopHint)
            # This connects the function to the combobox when changed
            self.dlg.comboBox.clear()
            
            # look here for the inputs
            path = os.path.join(QgsApplication.qgisSettingsDirPath(), r"python\plugins\stressor_receptor_calc\inputs")
            path = os.path.join(path,'*.{}'.format('csv'))
            path = path.replace(os.sep, '/')
            result = glob.glob(path)
            fields = sorted([os.path.basename(f).split(".csv")[0] for f in result])
            self.dlg.comboBox.addItems(fields)
            
            # this loads the inputs and populates the layer combobox
            self.select_calc_type(fields)
            
            # This connects the function to the layer combobox when changed
            self.dlg.comboBox.currentIndexChanged.connect(lambda: self.select_calc_type(fields))
           
            #sfields = ['TAUMAX', 'VEL']
            sfields = ['TAUMAX -Structured', 'TAUMAX -Unstructured', 'VEL -Structured', 'VEL -Unstructured']
            self.dlg.stressor_comboBox.addItems(sfields)
            
            # this connecta selecting the files. Since each element has a unique label seperate functions are used.
            
            # deprecated
            # self.dlg.pushButton.clicked.connect(self.select_receptor_file)
            #self.dlg.pushButton_2.clicked.connect(self.select_stressor_file)

            # set the present and not present files. Either .nc files or .tif folders
            self.dlg.pushButton.clicked.connect(lambda: self.select_device_file("present"))
            self.dlg.pushButton_5.clicked.connect(lambda: self.select_device_file("not present"))
            
            # set the boundary and run order files
            self.dlg.pushButton_6.clicked.connect(self.select_bc_file)
            self.dlg.pushButton_7.clicked.connect(self.select_run_order_file)
            
            # set the crs file
            self.dlg.crs_button.clicked.connect(self.select_crs)
            
            # set the receptor file
            self.dlg.receptor_button.clicked.connect(self.select_receptor_file)
            
            # set the secondary constraint
            self.dlg.pushButton_3.clicked.connect(self.select_secondary_constraint_file)
            # set the output
            self.dlg.pushButton_4.clicked.connect(self.select_output_file)
        
        # deprecated
        #self.dlg.lineEdit.clear()
        #self.dlg.lineEdit_2.clear()
        
        self.dlg.device_present.clear()
        self.dlg.device_not_present.clear()
        self.dlg.bc_prob.clear()
        self.dlg.run_order.clear()
        self.dlg.crs.clear()
        self.dlg.receptor_file.clear()
        self.dlg.sc_file.clear()
        self.dlg.ofile.clear()
        
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here
            # this grabs the files for input and output
                        
            dpresentfname = self.dlg.device_present.text()
            # ADD in an ini file here?
            if '.ini' not in dpresentfname:                
                dnotpresentfname = self.dlg.device_not_present.text()
                bcfname = self.dlg.bc_prob.text()
                rofname = self.dlg.run_order.text()
                
                rfilename = self.dlg.receptor_file.text()
                scfilename = self.dlg.sc_file.text()
                ofilename = self.dlg.ofile.text()
                
                svar = self.dlg.stressor_comboBox.currentText()
                
                crs = int(self.dlg.crs.text())
            else:
                 config = configparser.ConfigParser()
                 config.read(dpresentfname)
                 # For QA
                 configfile = dpresentfname
                 # after reading in the ini overwrite the variable
                 dpresentfname = config['Input']['Device Present Filepath']
                 dnotpresentfname = config['Input']['Device Not Present Filepath']
                 bcfname = config['Input']['Boundary Condition Filepath']
                 rofname = config['Input']['Run Order Filepath']
                 
                 svar = config['Input']['Stressor variable']
                 crs = int(config['Input']['Coordinate Reference System'])
                 
                 rfilename = config['Input']['Receptor Filepath']
                 scfilename = config['Input']['Secondary Constraint Filepath']
                 
                 ofilename = config['Output']['Output Filepath']
                 
            
            # create logger
            logger = logging.getLogger(__name__)
            logger.setLevel(logging.INFO)

            # create file handler and set level to info
            fname = ofilename.replace(".tif", '_{}.log'.format(date.today().strftime('%Y%m%d')))
            fh = logging.FileHandler(fname, mode='a', encoding='utf8')
            fh.setLevel(logging.INFO)

            # create formatter
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

            # add formatter to ch
            fh.setFormatter(formatter)

            # add ch to logger
            logger.addHandler(fh)

            # Set up the stressor name            
            sfilename = os.path.join(os.path.dirname(ofilename), "calculated_stressor.tif")
            srclassfilename = os.path.join(os.path.dirname(ofilename), "calculated_stressor_reclassified.tif")
           
            # message
            logger.info('Receptor File: {}'.format(rfilename))
            logger.info('Stressor File: {}'.format(sfilename))
            logger.info('Reclassified Stressor File: {}'.format(srclassfilename))
            logger.info('Device present File: {}'.format(dpresentfname))
            logger.info('Device not present File: {}'.format(dnotpresentfname))
            logger.info('Boundary Condition File: {}'.format(bcfname))
            logger.info('Run Order File: {}'.format(rofname))
            logger.info('Stressor: {}'.format(svar))
            logger.info('CRS: {}'.format(crs))
            logger.info('Secondary Constraint File: {}'.format(scfilename))
            logger.info('Output File: {}'.format(ofilename))
            
            
            # this grabs the current Table Widget values
            # calc_index=self.dlg.comboBox.currentIndex()
            # min_rc = self.dlg.tableWidget.item(calc_index, 1).text()
            # max_rc = self.dlg.tableWidget.item(calc_index, 2).text()
            
            # get the current style file paths
            profilepath = QgsApplication.qgisSettingsDirPath()
            profilepath = os.path.join(profilepath, "python", "plugins", "stressor_receptor_calc", "inputs", "Layer Style")
            rstylefile = os.path.join(profilepath, self.dlg.tableWidget.item(0, 1).text()).replace("\\", "/")
            sstylefile = os.path.join(profilepath, self.dlg.tableWidget.item(1, 1).text()).replace("\\", "/")
            scstylefile = os.path.join(profilepath, self.dlg.tableWidget.item(2, 1).text()).replace("\\", "/")
            
            if self.dlg.tableWidget.item(3, 1).text() != "":
                ostylefile = os.path.join(profilepath, self.dlg.tableWidget.item(3, 1).text()).replace("\\", "/")
            else:
                ostylefile = ""
                
            # deprecated for now
            #reclass_breakval = float(self.dlg.tableWidget.item(4, 1).text())
            
            logger.info('Receptor Style File: {}'.format(rstylefile))
            logger.info('Stressor Style File: {}'.format(sstylefile))
            logger.info('Secondary Constraint Style File: {}'.format(scstylefile))
            logger.info('Output Style File: {}'.format(ostylefile))
            #logger.info('Stressor reclassification break value: {}'.format(reclass_breakval))
          
            
            
             
            #QgsMessageLog.logMessage(min_rc + " , " + max_rc, level =Qgis.MessageLevel.Info)
            # if the output file path is empty display a warning
            if ofilename == "":
                QgsMessageLog.logMessage("Output file path not given.", level =Qgis.MessageLevel.Warning)
            
            #self.dlg.tableWidget.findItems(i,j, QTableWidgetItem(item))
            
            # calculate the raster from the NetCDF            
            if '.nc' in dpresentfname:
                if svar == 'TAUMAX -Structured':
                    sfilename, srclassfilename = self.calculate_stressor(dpresentfname,dnotpresentfname, bcfname, rofname, 'TAUMAX', crs, sfilename, srclassfilename, rfilename)
            
            # if there's .tif in the device present file than loop through the
            # tif files to build the stressor raster-
            if '.tif' in dpresentfname:
                # get the folder base names
                dpresntdir = os.path.dirname(dpresentfname)
                dnotpresntdir = os.path.dirname(dnotpresentfname)
                
                # read in the boundary conditions
                df_bc = pd.read_csv(bcfname)
                
                # set up a file list to append to
                tmpfiles = []
                
                
                for pfile, notpfile in zip(glob.glob(os.path.join(dpresntdir, '*.tif')), glob.glob(os.path.join(dnotpresntdir, '*.tif'))):
                    # loop through the files in the folder and apply the probability for subtraction
                    # get the base name for filtering 
                    pbase = os.path.basename(pfile)
                    notpbase = os.path.basename(notpfile)
                    prob = df_bc.loc[((df_bc.loc[:, 'cec filename'] == pbase) & (df_bc.loc[:, 'no cec filename'] == notpbase)), 'prob'].values[0] 
                    
                    # create a temp file to write to.
                    tpath = tempfile.NamedTemporaryFile(suffix='.tif').name
                    
                    tpath = self.raster_subtract(pfile, notpfile, tpath, prob = prob)
                    tmpfiles.append(tpath)
                # if we only have 1 file then set it to the output name and remove the temporary file
                # this sets the resulting addition to the output name
                if len(tmpfiles) == 1:
                    shutil.copy2(ofilename, tmpfiles[0])
                    os.remove(tmpfiles[0])
                else:
                    # if there's a receptor set this as the receptor layer
                    if rfilename != "":
                        sfilename = self.raster_add(tmpfiles, sfilename)
                    # if not use it as an output file
                    else:
                        ofilename = self.raster_add(tmpfiles, ofilename)
                    # remove the tmp files
                    [os.remove(tmpfile) for tmpfile in tmpfiles]
              
            # save the stressor as the output
            shutil.copy(sfilename, ofilename)

            # add and style the receptor
            self.style_layer(rfilename, rstylefile, checked = False)            
            
            if not scfilename == "":
                # add and style the secondary constraint
                self.style_layer(scfilename, scstylefile, checked = False)
            
            
            
            # add and style the outfile returning values
            self.style_layer(ofilename, ostylefile, ranges = True)
                
            self.export_area(ofilename, crs, ostylefile = None)
            
            # close and remove the filehandler
            fh.close()
            logger.removeHandler(fh)
            
