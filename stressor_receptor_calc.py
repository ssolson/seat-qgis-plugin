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
from qgis.core import QgsProject, Qgis, QgsApplication, QgsVectorLayer, QgsMessageLog, QgsRasterLayer, QgsRasterBandStats
from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
from qgis.gui import QgsLayerTreeView

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

# grab the data time
from datetime import date
import logging

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
                   
    def select_receptor_file(self):
        """ input the receptor file """
        filename, _filter = QFileDialog.getOpenFileName(
        self.dlg, "Select Receptor","", '*.tif')
        self.dlg.lineEdit.setText(filename)
    
    def select_stressor_file(self):
        """ input the stressor file which has had a threshold appiled to it """
        filename, _filter = QFileDialog.getOpenFileName(
        self.dlg, "Select Stressor","", '*.tif')
        self.dlg.lineEdit_2.setText(filename)
        
    def select_secondary_constraint_file(self):
        filename, _filter = QFileDialog.getOpenFileName(
        self.dlg, "Select Secondary Constraint","", '*.tif')
        self.dlg.lineEdit_3.setText(filename)
    
    def select_output_file(self):
        filename, _filter = QFileDialog.getSaveFileName(
        self.dlg, "Select Output","", '*.tif')
        self.dlg.lineEdit_4.setText(filename)
        
    def raster_multi(self, r, t, sc, opath):
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
        
        #Define threshold
        tbasename = os.path.splitext(os.path.basename(t))[0]
        
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
            params = { 'CELLSIZE' : None, 'CRS' : None, 'EXPRESSION' : '\"' + rbasename + '@1\" * \"' + tbasename + '@1\"', 
            'EXTENT' : None, 'LAYERS' : [r, t], 
            'OUTPUT' : opath}
        else:
            params = { 'CELLSIZE' : None, 'CRS' : None, 'EXPRESSION' : '\"' + rbasename + '@1\" * \"' + tbasename + '@1\" * \"' + scbasename + '@1\"', 
            'EXTENT' : None, 'LAYERS' : [r, t, sc], 
            'OUTPUT' : opath}

        processing.run("qgis:rastercalculator", params)
        
    def style_layer(self, fpath, stylepath, checked = True, ranges = True):
        # add the result layer to map
        basename = os.path.splitext(os.path.basename(fpath))[0]
        layer = QgsProject.instance().addMapLayer(QgsRasterLayer(fpath, basename))
        
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
    
    def export_area(self, ranges, ofilename):
        rdata = gdal.Open(ofilename)
        band1 = rdata.GetRasterBand(1)
        raster1 = band1.ReadAsArray()

        count = dict(zip(*np.unique(raster1, return_counts=True)))
        keys = list(count.keys())
        keys = [k for k in keys if k > 0]
        
        # make sure we have the same length keys and labels
        assert len(keys) == len(ranges)
        count = { ranges[i]: count[k] for i, k in enumerate(keys) }
        df = pd.DataFrame(list(count.items()), columns = ["symbol", "count"])
        
        basename = os.path.splitext(os.path.basename(ofilename))[0]
        layer = QgsRasterLayer(ofilename, basename)
        
        pixel_size_x = layer.rasterUnitsPerPixelX()
        pixel_size_y = layer.rasterUnitsPerPixelY()
        
        units = ""
        if layer.crs().mapUnits() ==  0:
            units = "m"
        
        
        df['area'] = df['count'] / (pixel_size_x * pixel_size_y)
        df['percent'] = (df['area']/sum(df['area'])) * 100.
        df2 = pd.DataFrame(index = [0])
        df2["symbol"] = "Total Area"
        df2["area"] = sum(df['area'])
        df2['percent'] = 100.

        df = df.append(df2, ignore_index=True)
        
        df['unit'] = units +'^2'
        df = df[['symbol', 'area', 'unit', 'percent']]
        
        # this overwrites
        df.to_csv(ofilename.replace(".tif", ".csv"), index = False)
        
    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False
            self.dlg = StressorReceptorCalcDialog()
            # This connects the function to the combobox when changed
            self.dlg.comboBox.clear()
            # look here for the inputs
            path = os.path.join(QgsApplication.qgisSettingsDirPath(), r"python\plugins\stressor_receptor_calc\inputs")
            path = os.path.join(path,'*.{}'.format('csv'))
            path = path.replace(os.sep, '/')
            result = glob.glob(path)
            fields = sorted([os.path.basename(f).split(".csv")[0] for f in result])
            self.dlg.comboBox.addItems(fields)
            # set to the first field
            self.select_calc_type(fields)
            
            # This connects the function to the layer combobox when changed
            self.dlg.comboBox.currentIndexChanged.connect(lambda: self.select_calc_type(fields))

            # this connecta selecting the files. Since each element has a unique label seperate functions are used.
            
            self.dlg.pushButton.clicked.connect(self.select_receptor_file)
            self.dlg.pushButton_2.clicked.connect(self.select_threshold_file)
            self.dlg.pushButton_3.clicked.connect(self.select_secondary_constraint_file)
            self.dlg.pushButton_4.clicked.connect(self.select_output_file)
        
        self.dlg.lineEdit.clear()
        self.dlg.lineEdit_2.clear()
        self.dlg.lineEdit_3.clear()
        self.dlg.lineEdit_4.clear()
        
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here
            # this grabs the files for input and output
            rfilename = self.dlg.lineEdit.text()
            sfilename = self.dlg.lineEdit_2.text()
            scfilename = self.dlg.lineEdit_3.text()
            ofilename = self.dlg.lineEdit_4.text()
            
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

            # message
            logger.info('Receptor File: {}'.format(rfilename))
            logger.info('Stressor File: {}'.format(sfilename))
            logger.info('Secondary Constraint File: {}'.format(rfilename))
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
            ostylefile = os.path.join(profilepath, self.dlg.tableWidget.item(3, 1).text()).replace("\\", "/")
            
             
            #QgsMessageLog.logMessage(min_rc + " , " + max_rc, level =Qgis.MessageLevel.Info)
            # if the output file path is empty display a warning
            if ofilename == "":
                QgsMessageLog.logMessage("Output file path not given.", level =Qgis.MessageLevel.Warning)
            
            #self.dlg.tableWidget.findItems(i,j, QTableWidgetItem(item))
            
            self.raster_multi(rfilename, sfilename, scfilename, ofilename)
            
            # add the result layer to map
            #basename = os.path.splitext(os.path.basename(ofilename))[0]
            #layer = QgsProject.instance().addMapLayer(QgsRasterLayer(ofilename, basename))
            
            # apply layer style
            #layer.loadNamedStyle(r"C:\Users\ependleton52\Desktop\temp (local)\QGIS\Layer Style\receptor_rc.qml")
            # stylefile = r"C:\Users\ependleton52\Desktop\temp (local)\QGIS\Layer Style\receptor_rc.qml"
            # tstylefile = r"C:\Users\ependleton52\Desktop\temp (local)\QGIS\Layer Style\threshold_rc.qml"
            # scstylefile = r"C:\Users\ependleton52\Desktop\temp (local)\QGIS\Layer Style\constriant_rc.qml"
            
            # add and style the receptor
            self.style_layer(rfilename, rstylefile, checked = False)
            
            # add and style the stressor which has a threshold applied
            self.style_layer(sfilename, sstylefile, checked = False)
            
            if not scfilename == "":
                # add and style the secondary constraint
                self.style_layer(scfilename, scstylefile, checked = False)
            
            # add and style the outfile returning values
            ranges = self.style_layer(ofilename, ostylefile, ranges = True)
            self.export_area(ranges, ofilename)
            
            # close and remove the filehandler
            fh.close()
            logger.removeHandler(fh)
            
    
