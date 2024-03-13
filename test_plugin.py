# -*- coding: utf-8 -*-
"""
/***************************************************************************
 TestPlugin
                                 A QGIS plugin
 test 01
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2024-03-05
        git sha              : $Format:%H$
        copyright            : (C) 2024 by test01
        email                : test@test
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
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction


from qgis.core import (
    Qgis,
    QgsProject, 
    QgsVectorLayer, 
    QgsRasterLayer,
    QgsMapLayer,
    QgsFeature, 
    QgsFeatureIterator, 
    QgsPointXY, 
    QgsMapLayerProxyModel,
    QgsTask,
    QgsMessageLog,
    QgsCoordinateTransform,
    QgsReferencedGeometryBase,
    QgsCoordinateReferenceSystem,
    QgsTaskManager
)

from sys import version_info

# Initialize Qt resources from file resources.py
from .resources import *

# Import the code for the DockWidget
from .test_plugin_dockwidget import TestPluginDockWidget
import os.path


VERSION = Qgis.QGIS_VERSION.split('.')[0:2]
MESSAGE_CATEGORY = "RoadTask"
TASK_DESCRIPTION = "ROAD_DEM_CALCULATION"


class ReferencedShaft(QgsReferencedGeometryBase): # луч в заданной СК -- сомнительное решение??
    def __init__(self, point, direction, crs=QgsCoordinateReferenceSystem(3857, QgsCoordinateReferenceSystem.EpsgCrsId)):
        super().__init__(crs)
        self.startPoint = point     # x0 y0 - начальные координаты
        self.direction  = direction # dx dy - направление луча, нормализованный вектор
        self.pointNum   = -1         # n - очередная точка на луче
        self.step       = 1         # шаг в заданной СК и ее ед.измерения, с которым определяется точка
        # Точка на луче
        # xn = x0 + n*step*dx
        # yn = y0 + n*step*dy
    
    def __str__(self):
        return f'Shaft of:\nPoint:{self.startPoint}\nDirection{self.direction}\nAt crs of:{self.crs()}'
    
    def at(self): # текущий указатель луча
        return self.pointNum
    
    def start(self): # указатель луча в начало
        self.pointNum = -1
    
    def setStep(self, nstep): # изменить шаг определения точки на луче (перезагружает луч)
        self.start()
        self.step = nstep
    
    def PointAt(self, num): # определение точки на луче с указанием номера
        return self.startPoint + self.direction*num*self.step
    
    def nextPoint(self): # след.точка
        self.pointNum+=1
        return self.PointAt(self.at())
    
    def pointOnShaft(self, point) -> bool: # принадлежит ли точка лучу
        norm = (point - self.startPoint).normalized()
        if (norm == self.direction):
            return True
        else:
            return False   
    
    def pointsOnShaftTo(self,point,step=1): # список из точек, расположенных на луче до указанной с выбранным шагом в СК
        if (self.pointOnShaft(point)):
            self.setStep(step)
            pointList = []
            
            Npoint = self.nextPoint()
            while abs(Npoint.x()) < abs(point.x()):
                pointList.append(Npoint)
                Npoint = self.nextPoint()
            
            return pointList
        else:
            return None

class CalculateTaskOptions(): # для передачи данных о свойствах задачи
    def __init__(self, dem_layer, lines, step, band):
        self.DemLayer = dem_layer   # QgsRasterLayer
        self.roadLines = lines      # QgsVectorLayer
        self.SampleStep = step      # numerical step of sampling raster
        self.BandNo = band          # integer, number of band

    def __str__(self):
        str_r = "Calculation Parameters\n"
        str_r += "Lines Layer: " + self.roadLines.name() + "\n"
        str_r += "DEM Layer: " + self.DemLayer.name() + " Band:" + str(self.BandNo) + "\n"
        str_r += "Sample Step: " + str(self.SampleStep) + " in " + str(self.DemLayer.crs().mapUnits())  + "\n"
        return str_r

class CalculateTask(QgsTask): # тестовая версия задачи
    def __init__(self, description, task_options):
        super().__init__(description, QgsTask.CanCancel)
        self.options = task_options
        self.result = None

    def run(self): # основная функция задачи     
        print('** Task run')
        current_progress = 0.0
        while (current_progress < 100):
            self.setProgress(current_progress)
            current_progress+=10

        return True
    
    def finished(self, result): # завершение задачи
        print('Task Ended with ' + str(result))
        self.result = 100
       
    def cancel(self): # отмена задачи
        super().cancel()


class TestPlugin:
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
            'TestPlugin_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Test Plugin')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'TestPlugin')
        self.toolbar.setObjectName(u'TestPlugin')

        #print "** INITIALIZING TestPlugin"

        self.pluginIsActive = False
        self.dockwidget = None


        self.task_manager = QgsTaskManager()
        self.task_manager.allTasksFinished.connect(self.allTasksFinished)
        self.task_manager.progressChanged.connect(self.taskProgresChanged)


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
        return QCoreApplication.translate('TestPlugin', message)


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
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action


    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/test_plugin/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u''),
            callback=self.run,
            parent=self.iface.mainWindow())

    #--------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        print( "** CLOSING TestPlugin")

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dockwidget = None

        self.pluginIsActive = False


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        print( "** UNLOAD TestPlugin")

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Test Plugin'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    #--------------------------------------------------------------------------

    def run(self):
        """Run method that loads and starts the plugin"""

        if not self.pluginIsActive:
            self.pluginIsActive = True

            print("** STARTING TestPlugin")

            # dockwidget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.dockwidget == None:
                print( "** Initialize dockwidget TestPlugin")
                # Create the dockwidget (after translation) and keep reference
                self.dockwidget = TestPluginDockWidget()

                self.dockwidget.mMapLayerComboBox_raster.layerChanged.connect(self.RasterDemLayerChanged)
                self.RasterDemLayerChanged(self.dockwidget.mMapLayerComboBox_raster.currentLayer())

                self.dockwidget.pushButton.clicked.connect(self.runTask)

                self.dockwidget.mMapLayerComboBox.setFilters(QgsMapLayerProxyModel.LineLayer) # загрузка фильтра слоев в QgsMapLayerComboBox
                self.dockwidget.mMapLayerComboBox_raster.setFilters(QgsMapLayerProxyModel.RasterLayer) # загрузка фильтра слоев в QgsMapLayerComboBox
                
            # connect to provide cleanup on closing of dockwidget
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)

            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.TopDockWidgetArea, self.dockwidget)
            self.dockwidget.show()
        
            
    def RasterDemLayerChanged(self, l):
        self.dockwidget.comboBox_band.clear()
        if (type(l) is QgsRasterLayer):
            for i in range(l.bandCount()):
                self.dockwidget.comboBox_band.addItem(str(i+1))

    def runTask(self): # тестирование запуск
        self.dockwidget.textEdit_log.clear()

        lineVector = self.dockwidget.mMapLayerComboBox.currentLayer()
        DemRaster = self.dockwidget.mMapLayerComboBox_raster.currentLayer()
        BandNo = self.dockwidget.comboBox_band.currentIndex()

        CoordVectoDemTransfer = QgsCoordinateTransform(lineVector.crs(), DemRaster.crs(), QgsProject.instance())
        # класс для трансформирования QgsReferencedGeometryBase в из одной СК в другую

        print("Vector layer in Dem crs extent:" , CoordVectoDemTransfer.transform(lineVector.extent()))
        print("Vector and Raster layer have interception? = ", DemRaster.extent().contains(CoordVectoDemTransfer.transform(lineVector.extent()))) 

        cto = CalculateTaskOptions(DemRaster, lineVector, self.dockwidget.doubleSpinBox_stepSize.value(), BandNo)
        self.dockwidget.textEdit_log.append(str(cto))
        newTask = CalculateTask(TASK_DESCRIPTION, cto)
        self.task_manager.addTask(newTask)

        newTask.taskCompleted.connect(self.CalcTaskComplete)

        
    
    def CalcTaskComplete(self): # коннект с классом задачи на ее завершение
        self.iface.messageBar().pushMessage("Finished calculating", level=Qgis.Success)

    def allTasksFinished(self): # все активные задачи завершены
        print("--------ALL-TASKS-FINISED-----------")
        for i, task in enumerate(self.task_manager.tasks()):
            self.dockwidget.textEdit_log.append("Task No " + str(i) + " Finished with " + str(task.result))
            del task
        
        # print(len(self.task_manager.tasks()))
        # print(self.task_manager.count())
    
    def taskProgresChanged(self, task_id, progress): # прогресс в задаче обновлен
        print(task_id, progress)