from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox, QgsMapToolEmitPoint
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel, QModelIndex
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar, QMenu, QHeaderView, QFileDialog
from PyQt5 import QtWidgets
from typing import Iterable
from datetime import datetime

from ..ch_siac_dialog_ancillaydata import Ui_ancillaryLayerDialog

from ..modules.SiacImportExport import SiacExporter, SiacImporter
from ..modules.SiacEnumerations import *
from ..modules.toolkitData.SiacDataSourceOptions import ProjectDataSourceOptions
from ..modules.QtUiWrapper import QtWrapper
from .SiacFoundation import Utilities

import os
import webbrowser

class QtUiMainDialogCallbacks:

    parent = None
    selectedLayerInLayerView = None

    def __init__(self, parent = None) -> None:
        self.parent = parent
    

    #
    # Progress reporting
    #
    #
    def createMessageBarWithProgress(self, message, messageLevel = Qgis.MessageLevel.Info):       
        if self.parent.progressMessageBar is not None: 
            self.parent.iface.messageBar().clearWidgets()

        self.parent.progressMessageBar = self.parent.iface.messageBar().createMessage(message)
        self.parent.progress = QProgressBar()
        self.parent.progress.setMaximum(100)
        self.parent.progressMessageBar.layout().addWidget(self.parent.progress)
        self.parent.iface.messageBar().pushWidget(self.parent.progressMessageBar, messageLevel)       

    def createMessageBar(self, message, messageLevel = Qgis.MessageLevel.Info):

        if self.parent.progressMessageBar is not None:
            self.parent.iface.messageBar().clearWidgets()   
        self.parent.iface.messageBar().pushMessage(message, messageLevel, duration = 5)
        self.updateStatusBarProgressMessage(message)


    def setProgressValue(self, value):
        self.parent.progress.setValue(value)
    
    def setMaximumProgressValue(self, value):
        self.parent.progress.setMaximum(value)

    def setProgressMessage(self, message, level):
        self.parent.progressMessageBar.setText(message)
        self.parent.progressMessageBar.setLevel(level) 
        self.updateStatusBarProgressMessage(message)

    def enableInternalProgressReporter(self, message):
        self.parent.dlg.internalProgress.setMaximum(0)
        self.parent.dlg.internalProgress.setMinimum(0)
        self.updateStatusBarProgressMessage(message)
        
    def disableInternalProgressReporter(self, message = ""):
        self.parent.dlg.internalProgress.setMaximum(100)
        self.parent.dlg.internalProgress.setMinimum(100)
        self.updateStatusBarProgressMessage(message)

    def updateStatusBarProgressMessage(self, message):
        self.parent.dlg.internalMessage.setText(message)        


    #
    # UI initialization, set default values
    # Connect functions
    #
    def applyOptionSet(self, options):
        # initialize with default tree canopy width/radius
        self.parent.dlg.textCanopyWidth.setText(str(options[SiacToolkitOptionValue.TCAC_PARAMS_TREE_CROWN_DIAMETER_VALUE]))
        self.parent.dlg.textStreetWidth.setText(str(options[SiacToolkitOptionValue.DATAPROCESSOR_PARAMS_STREET_WIDTH])) 
        # connectivity settings
        self.parent.dlg.textNnCount.setText(str(options[SiacToolkitOptionValue.CONNECTIVITY_PARAMS_NEIGHBOUR_COUNT]))
        self.parent.dlg.textConnectivityThreshold.setText(str(options[SiacToolkitOptionValue.CONNECTIVITY_PARAMS_THRESHOLD]))         
        self.parent.dlg.checkBoxBuildingsAsBarrier.setChecked(options[SiacToolkitOptionValue.CONNECTIVITY_PARAMS_BUILDINGS_AS_BARRIERS])        
        self.parent.dlg.textComponentDelta.setText(options[SiacToolkitOptionValue.CONNECTIVITY_PARAMS_FRAGMENTATION_DISTANCES])
        self.parent.dlg.checkBoxBetweennessCentralityIndicator.setChecked(options[SiacToolkitOptionValue.CONNECTIVITY_INDICATORS_BETWEENNESS])
        self.parent.dlg.checkBoxClosenessCentralityIndicator.setChecked(options[SiacToolkitOptionValue.CONNECTIVITY_INDICATORS_CLOSENESS])
        self.parent.dlg.checkBoxDegreeOfCentralityIndicator.setChecked(options[SiacToolkitOptionValue.CONNECTIVITY_INDICATORS_DEGREE_CENTRALITY])
        self.parent.dlg.checkBoxDiameterIndicator.setChecked(options[SiacToolkitOptionValue.CONNECTIVITY_INDICATORS_COMPONENT_DIAMETER])
        self.parent.dlg.checkBoxEccentricityIndicator.setChecked(options[SiacToolkitOptionValue.CONNECTIVITY_INDICATORS_ECCENTRICITY])
        # set default ecosystem service potentials/rates for regulation of air quality
        self.parent.dlg.coinRateAirQualitySO2.setText(str(options[SiacToolkitOptionValue.COIN_ESS_AIR_QUALITY_SO2_REMOVALRATE]))
        self.parent.dlg.coinRateAirQualityNO2.setText(str(options[SiacToolkitOptionValue.COIN_ESS_AIR_QUALITY_NO2_REMOVALRATE]))
        self.parent.dlg.coinRateAirQualityPM10.setText(str(options[SiacToolkitOptionValue.COIN_ESS_AIR_QUALITY_PM10_REMOVALRATE]))
        self.parent.dlg.coinRateAirQualityO3.setText(str(options[SiacToolkitOptionValue.COIN_ESS_AIR_QUALITY_O3_REMOVALRATE]))
        self.parent.dlg.coinRateAirQualityCO.setText(str(options[SiacToolkitOptionValue.COIN_ESS_AIR_QUALITY_CO_REMOVALRATE]))
        self.parent.dlg.checkBoxMediateEssInAssessment.setChecked(options[SiacToolkitOptionValue.COIN_ESS_MEDIATE_ESS])
        
        # set default ecosystem service potentialsU/rates for carbon storage and sequestration
        self.parent.dlg.coinRateCStorage.setText(str(options[SiacToolkitOptionValue.COIN_ESS_CARBON_STORAGERATE]))
        self.parent.dlg.coinRateCSequestration.setText(str(options[SiacToolkitOptionValue.COIN_ESS_CARBON_SEQUESTRATIONRATE]))        
        # SITA sampling options        
        self.parent.dlg.txtSitaSampleSize.setText(str(options[SiacToolkitOptionValue.SITA_PARAMS_SAMPLE_SIZE]))
        self.parent.dlg.txtSitaSampleDistanceThreshold.setText(str(options[SiacToolkitOptionValue.SITA_PARAMS_MIN_PATCHDISTANCE]))
        self.parent.dlg.txtSitaSampleDiameter.setText(str(options[SiacToolkitOptionValue.SITA_PARAMS_PATCHDIAMETER]))
        # anchor point
        self.parent.dlg.boxLinkAnchorPoint.setCurrentIndex(options[SiacToolkitOptionValue.CONNECTIVITY_PARAMS_ANCHOR_POINT])
        # tree layer field pickers
        self.parent.dlg.pickerTreeGenusField.setField(options[SiacToolkitOptionValue.TCAC_PARAMS_SPECIES_FIELDNAME])
        self.parent.dlg.pickerCrownDiameterField.setField(options[SiacToolkitOptionValue.TCAC_PARAMS_TREE_CROWN_DIAMETER_FIELDNAME])
        # ess mediation by tree health
        self.parent.dlg.checkBoxAssessEssScaling.setChecked(options[SiacToolkitOptionValue.TCAC_PARAMS_ASSESS_TREE_ESS_SCALING])
        self.parent.dlg.pickerTreeHealthField.setField(options[SiacToolkitOptionValue.TCAC_PARAMS_TREE_HEALTH_FIELDNAME])
        # tree crown diameter basis
        self.parent.dlg.radioTcdUserValue.setChecked(options[SiacToolkitOptionValue.TCAC_PARAMS_USER_DEFINED_TREE_CROWN_DIAMETER])
        self.parent.dlg.radioTcdFieldValue.setChecked(not options[SiacToolkitOptionValue.TCAC_PARAMS_USER_DEFINED_TREE_CROWN_DIAMETER])
        self.updateTreeCoverModellingUi()

        # fruit tree specification
        self.parent.dlg.textFruitTreeSpecification.setPlainText( ";".join(options[SiacToolkitOptionValue.TCAC_PARAMS_FRUITTREE_SPECIES_LIST]) )  
        # lst regression options
        self.parent.dlg.pickerRegressionPredictorType.setCurrentText(options[SiacToolkitOptionValue.COIN_ESS_COOLING_PREDS_COVERTYPE])
        self.parent.dlg.pickerPredictorChoice.setCurrentText(options[SiacToolkitOptionValue.COIN_ESS_COOLING_PREDS_INCLUDE_IMPV])
        self.parent.dlg.checkBoxIncludeSupportedAncillaryTypes.setChecked(options[SiacToolkitOptionValue.COIN_ESS_COOLING_INCLUDE_ANCILLARY_ENTITIES])
        self.parent.dlg.checkBoxSitaLstIncludeLowess.setChecked(options[SiacToolkitOptionValue.COIN_ESS_COOLING_INCLUDE_LOWESS])
        # typology params
        self.parent.dlg.txtForestRelativeTreeCoverThreshold.setText(str(options[SiacToolkitOptionValue.TYPOLOGY_FOREST_RELATIVE_TREE_COVER_THRESHOLD]))
        self.parent.dlg.txtForestMinimumAreaThreshold.setText(str(options[SiacToolkitOptionValue.TYPOLOGY_FOREST_MINIMUM_AREA_THRESHOLD]))
        self.parent.dlg.txtLinearityThreshold.setText(str(options[SiacToolkitOptionValue.TYPOLOGY_LINEARITY_THRESHOLD]))        
        self.parent.dlg.txtAdjacencyThreshold.setText(str(options[SiacToolkitOptionValue.TYPOLOGY_NEAR_THRESHOLD]))


    def getOptionValue(self, cOption : SiacToolkitOptionValue) -> any:
        
        if cOption == SiacToolkitOptionValue.TCAC_PARAMS_USER_DEFINED_TREE_CROWN_DIAMETER:
            return self.parent.dlg.radioTcdUserValue.isChecked()        
        if cOption == SiacToolkitOptionValue.TCAC_PARAMS_TREE_CROWN_DIAMETER_VALUE:
            return float(self.parent.dlg.textCanopyWidth.text())
        if cOption == SiacToolkitOptionValue.TCAC_PARAMS_TREE_CROWN_DIAMETER_FIELDNAME:
            return self.parent.dlg.pickerCrownDiameterField.currentField()        
        elif cOption == SiacToolkitOptionValue.TCAC_PARAMS_SPECIES_FIELDNAME:
            return self.parent.dlg.pickerTreeGenusField.currentField()        
        elif cOption == SiacToolkitOptionValue.TCAC_PARAMS_FRUITTREE_SPECIES_LIST:
            return self.parent.dlg.textFruitTreeSpecification.toPlainText().split(';')
        elif cOption == SiacToolkitOptionValue.TCAC_PARAMS_ASSESS_TREE_ESS_SCALING:
            return self.parent.dlg.checkBoxAssessEssScaling.isChecked()
        elif cOption == SiacToolkitOptionValue.TCAC_PARAMS_TREE_HEALTH_FIELDNAME:
            return self.parent.dlg.pickerTreeHealthField.currentField()
        
        elif cOption == SiacToolkitOptionValue.DATAPROCESSOR_PARAMS_STREET_WIDTH:
            return float(self.parent.dlg.textStreetWidth.text())
        
        elif cOption == SiacToolkitOptionValue.CONNECTIVITY_PARAMS_NEIGHBOUR_COUNT:
            return float(self.parent.dlg.textNnCount.text())
        elif cOption == SiacToolkitOptionValue.CONNECTIVITY_PARAMS_THRESHOLD:
            return float(self.parent.dlg.textConnectivityThreshold.text())
        elif cOption == SiacToolkitOptionValue.CONNECTIVITY_INDICATORS_BETWEENNESS:
            return self.parent.dlg.checkBoxBetweennessCentralityIndicator.isChecked()
        elif cOption == SiacToolkitOptionValue.CONNECTIVITY_INDICATORS_CLOSENESS:
            return self.parent.dlg.checkBoxClosenessCentralityIndicator.isChecked()
        elif cOption == SiacToolkitOptionValue.CONNECTIVITY_INDICATORS_DEGREE_CENTRALITY:
            return self.parent.dlg.checkBoxDegreeOfCentralityIndicator.isChecked()
        elif cOption == SiacToolkitOptionValue.CONNECTIVITY_INDICATORS_COMPONENT_DIAMETER:
            return self.parent.dlg.checkBoxDiameterIndicator.isChecked()
        elif cOption == SiacToolkitOptionValue.CONNECTIVITY_INDICATORS_ECCENTRICITY:
            return self.parent.dlg.checkBoxEccentricityIndicator.isChecked()
        elif cOption == SiacToolkitOptionValue.CONNECTIVITY_PARAMS_BUILDINGS_AS_BARRIERS:
            return self.parent.dlg.checkBoxBuildingsAsBarrier.isChecked()
        elif cOption == SiacToolkitOptionValue.CONNECTIVITY_PARAMS_ANCHOR_POINT:
            return self.parent.dlg.boxLinkAnchorPoint.currentIndex()
        elif cOption == SiacToolkitOptionValue.CONNECTIVITY_PARAMS_FRAGMENTATION_DISTANCES:
            return self.parent.dlg.textComponentDelta.text()
        
        elif cOption == SiacToolkitOptionValue.SITA_PARAMS_SAMPLE_SIZE:
            return int(self.parent.dlg.txtSitaSampleSize.text())
        elif cOption == SiacToolkitOptionValue.SITA_PARAMS_MIN_PATCHDISTANCE:
            return float(self.parent.dlg.txtSitaSampleDistanceThreshold.text())
        elif cOption == SiacToolkitOptionValue.SITA_PARAMS_PATCHDIAMETER:
            return float(self.parent.dlg.txtSitaSampleDiameter.text())
        
        elif cOption == SiacToolkitOptionValue.COIN_ESS_AIR_QUALITY_SO2_REMOVALRATE:
            return float(self.parent.dlg.coinRateAirQualitySO2.text())
        elif cOption == SiacToolkitOptionValue.COIN_ESS_AIR_QUALITY_NO2_REMOVALRATE:
            return float(self.parent.dlg.coinRateAirQualityNO2.text())
        elif cOption == SiacToolkitOptionValue.COIN_ESS_AIR_QUALITY_PM10_REMOVALRATE:
            return float(self.parent.dlg.coinRateAirQualityPM10.text())
        elif cOption == SiacToolkitOptionValue.COIN_ESS_AIR_QUALITY_O3_REMOVALRATE:
            return float(self.parent.dlg.coinRateAirQualityO3.text())
        elif cOption == SiacToolkitOptionValue.COIN_ESS_AIR_QUALITY_CO_REMOVALRATE:
            return float(self.parent.dlg.coinRateAirQualityCO.text())
        elif cOption == SiacToolkitOptionValue.COIN_ESS_CARBON_STORAGERATE:
            return float(self.parent.dlg.coinRateCStorage.text())
        elif cOption == SiacToolkitOptionValue.COIN_ESS_CARBON_SEQUESTRATIONRATE:
            return float(self.parent.dlg.coinRateCSequestration.text())
        elif cOption == SiacToolkitOptionValue.COIN_ESS_COOLING_PREDS_COVERTYPE:
            return self.parent.dlg.pickerRegressionPredictorType.currentText()
        elif cOption == SiacToolkitOptionValue.COIN_ESS_COOLING_PREDS_INCLUDE_IMPV:
            return self.parent.dlg.pickerPredictorChoice.currentText()
        elif cOption == SiacToolkitOptionValue.COIN_ESS_COOLING_INCLUDE_ANCILLARY_ENTITIES:
            return self.parent.dlg.checkBoxIncludeSupportedAncillaryTypes.isChecked()
        elif cOption == SiacToolkitOptionValue.COIN_ESS_COOLING_INCLUDE_LOWESS:
            return self.parent.dlg.checkBoxSitaLstIncludeLowess.isChecked()
        elif cOption == SiacToolkitOptionValue.COIN_ESS_MEDIATE_ESS:
            return self.parent.dlg.checkBoxMediateEssInAssessment.isChecked()
        
        elif cOption == SiacToolkitOptionValue.TYPOLOGY_FOREST_RELATIVE_TREE_COVER_THRESHOLD:
            return float(self.parent.dlg.txtForestRelativeTreeCoverThreshold.text())
        elif cOption == SiacToolkitOptionValue.TYPOLOGY_FOREST_MINIMUM_AREA_THRESHOLD:
            return float(self.parent.dlg.txtForestMinimumAreaThreshold.text())
        elif cOption == SiacToolkitOptionValue.TYPOLOGY_LINEARITY_THRESHOLD:
            return float(self.parent.dlg.txtLinearityThreshold.text())
        elif cOption == SiacToolkitOptionValue.TYPOLOGY_NEAR_THRESHOLD:
            return float(self.parent.dlg.txtAdjacencyThreshold.text())
        
        return None

    def collectOptionSet(self):
        options = {}        
        for cOption in SiacToolkitOptionValue:
            options[cOption] = self.getOptionValue(cOption=cOption)       
        return options

    def setProjectCrs(self):
        # get map canvas CRS
        # this requires deleting all datasources from project, as their CRS may have differed
        self.btnRemoveAllRowsClickEventHandler()
        ProjectDataSourceOptions.Crs = QgsProject.instance().crs().authid().split(":")[1]
        self.parent.dlg.labelEpsg.setText('EPSG:{}'.format(ProjectDataSourceOptions.Crs))

    def defineUiDefaultValues(self, options):

        # tool window progress and messaging default values
        self.disableInternalProgressReporter()
        self.parent.dlg.outputTextBox.setFontPointSize(8)

        # update project crs
        self.setProjectCrs()
        
        # initialize data type selection
        self.updatePickerDataLayerTypes()

        # regression for LST
        # update combo box for cover type used
        for predType in LocalRegressionConverType:
            self.parent.dlg.pickerRegressionPredictorType.addItem(predType.value)
        # update combo box for impv cover selection 
        for predType in LstRegressionPredictorSet:
            self.parent.dlg.pickerPredictorChoice.addItem(predType.value) 
        
        self.parent.dlg.btnConfirmFruitTreeSpecificationChange.setEnabled(False)

        # populate with link anchor points
        self.parent.dlg.boxLinkAnchorPoint.addItem("Edge")
        self.parent.dlg.boxLinkAnchorPoint.addItem("Centroid")

        # set perimeter tool default value
        #self.parent.dlg.perimeterValueSlider.setValue(50)

        self.open_ancillary_data_editor_action.setEnabled(False)        
        self.applyOptionSet(options)

    def updateTreeCoverModellingUi(self):
        if self.parent.dlg.radioTcdUserValue.isChecked():
            # show crown diameter value field
            self.parent.dlg.pickerCrownDiameterField.setVisible(False)
            self.parent.dlg.pickerCrownDiameterField.setField(None)

            self.parent.dlg.textCanopyWidth.setVisible(True)

        else:
            # show crown diameter picker
            self.parent.dlg.pickerCrownDiameterField.setVisible(True)
            self.parent.dlg.textCanopyWidth.setVisible(False)

        if self.parent.dlg.checkBoxAssessEssScaling.isChecked():
            self.parent.dlg.pickerTreeHealthField.setVisible(True)
            self.parent.dlg.pickerTreeHealthField.setEnabled(True)
        else:
            self.parent.dlg.pickerTreeHealthField.setVisible(False)
            self.parent.dlg.pickerTreeHealthField.setEnabled(False)
            self.parent.dlg.pickerTreeHealthField.setField(None)


    

    def setupUiAtFirstStart(self, options):
        self.defineUiCallbacks()
        self.defineUiDefaultValues(options)


    def defineUiCallbacks(self):
        self.parent.dlg.btnRemoveSelectedRow.clicked.connect(self.uiCallbackRemoveSelectedRows)
        self.parent.dlg.btnAddDataSource.clicked.connect(self.parent.uiCallbackAddDataSourceToList)

        # some essential layerview events
        self.parent.dlg.layerView.doubleClicked.connect(self.layerTableDoubleClickedEventHandler)
        self.parent.dlg.layerView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.parent.dlg.layerView.customContextMenuRequested.connect(self.aboutToShowDataSourcesLayerListContextMenu)
        
        selectionModel = self.parent.dlg.layerView.selectionModel()
        selectionModel.selectionChanged.connect(self.dataSourceLayerListSelectionChanged)

        # parameters toolbox events and default state for tree cover modelling        
        self.parent.dlg.radioTcdUserValue.toggled.connect(self.updateTreeCoverModellingUi)
        self.parent.dlg.checkBoxAssessEssScaling.toggled.connect(self.updateTreeCoverModellingUi)

        # TODO: Readd these functions at some point
        # import/export buttons: connect to event handlers
        #self.parent.dlg.btnExportConnectivityGraph.clicked.connect(self.parent.exportGraph)
        #self.parent.dlg.btnExportExtractedLstData.clicked.connect(self.parent.exportRegressionParamsObject)
        #self.parent.dlg.btnImportExtractedLstData.clicked.connect(self.parent.importRegressionParamsObject)


        # perimeter map tool slider and text box
        #self.parent.dlg.perimeterValueSlider.valueChanged.connect(self.perimeterToolSliderValueChangedEventHandler)
        
        # connect events, and disable tree genus/species field picker
        self.parent.dlg.textFruitTreeSpecification.textChanged.connect(self.fruitTreeTextChangedEventHandler)           
        self.parent.dlg.btnConfirmFruitTreeSpecificationChange.clicked.connect(self.fruitTreeTextChangedButtonEventHandler)   
        self.disableTreeLayerFieldPickers()

        self.setActiveLayerFieldText(None)
        
    #
    # Further event handlers
    #
    #
    def setActiveLayerFieldText(self, txt):
        txtToSet = "No active layer" if txt is None else txt
        col = '#FF0000' if txt is None else '#00FF00'

        styleSheet = "QFrame{background-color: '%s';}" % col
        self.parent.dlg.statusActiveLayer.setStyleSheet(styleSheet)
        self.parent.dlg.txtActiveLayer.setText(txtToSet)

    def fruitTreeTextChangedEventHandler(self):
        self.parent.dlg.btnConfirmFruitTreeSpecificationChange.setEnabled(True)
    
    def fruitTreeTextChangedButtonEventHandler(self):
        self.parent.params['OPTIONS']['FRUIT_TREE_GENUS_LIST'] = self.parent.dlg.textFruitTreeSpecification.toPlainText().split(';')
        self.parent.dlg.textFruitTreeSpecification.setPlainText(";".join(self.parent.params['OPTIONS']['FRUIT_TREE_GENUS_LIST']))
        self.parent.dlg.internalMessage.setText("Changes applied.")
        self.parent.dlg.btnConfirmFruitTreeSpecificationChange.setEnabled(False)

    def perimeterToolSliderValueChangedEventHandler(self, value):        
        self.parent.dlg.labelPerimeterValue.setText(str(value))



    def btnRemoveAllRowsClickEventHandler(self):
        self.parent.resetDataStore()
        self.disableTreeLayerFieldPickers()
        self.updatePickerDataLayerTypes()


    

    def enableTreeLayerFieldPickers(self, treeLayer : QgsVectorLayer):
        # enable tree-layer based field pickers, assign layer to each picker
        # species/genus picker
        self.parent.dlg.pickerTreeGenusField.setEnabled(True)        
        self.parent.dlg.pickerTreeGenusField.setLayer(treeLayer)
        self.parent.dlg.pickerTreeGenusField.setField(None)
        # crown diameter picker
        self.parent.dlg.pickerCrownDiameterField.setEnabled(True)        
        self.parent.dlg.pickerCrownDiameterField.setLayer(treeLayer)
        self.parent.dlg.pickerCrownDiameterField.setField(None)
        # tree health picker
        self.parent.dlg.pickerTreeHealthField.setLayer(treeLayer)
        self.parent.dlg.pickerTreeHealthField.setField(None)
        
    def disableTreeLayerFieldPickers(self):
        # reset tree-layer based field pickers, as no data source is currently present
        # species/genus picker
        self.parent.dlg.pickerTreeGenusField.setLayer(None)
        self.parent.dlg.pickerTreeGenusField.setPlaceholderText("Define a Tree Cadastre Layer to Continue")
        self.parent.dlg.pickerTreeGenusField.setEnabled(False)
        # crown diameter picker
        self.parent.dlg.pickerCrownDiameterField.setLayer(None)
        self.parent.dlg.pickerCrownDiameterField.setPlaceholderText("Define a Tree Cadastre Layer to Continue")
        self.parent.dlg.pickerCrownDiameterField.setEnabled(False)
        # tree health picker
        self.parent.dlg.pickerTreeHealthField.setLayer(None)
        self.parent.dlg.pickerTreeHealthField.setPlaceholderText("Define a Tree Cadastre Layer to Continue")
 
    def getSingleSelectedRowIndex(self):
        # here, we need to take care of user selection
        selectedRows = self.parent.dlg.layerView.selectedIndexes()
        selectedItems = []
        for r in selectedRows:
            if not r.row() in selectedItems:
                selectedItems.append(r.row())
        return None if len(selectedItems) == 0 or len(selectedItems) > 1 else selectedItems[0]

    def uiCallbackRemoveSelectedRows(self):
        selectedRows = self.parent.dlg.layerView.selectedIndexes()
        rowsToRemove = []
        for r in selectedRows:
            # r is a QModelIndex object            
            # r.row() gives the index to remove
            if r.row() not in rowsToRemove:
                rowsToRemove.append(r.row())

        if len(rowsToRemove) > 0:
            for idx in reversed(rowsToRemove):
                self.removeItemAtIndexFromListOfLayers(idx)
                
            
        self.parent.dlg.layerView.clearSelection()

    def removeItemAtIndexFromListOfLayers(self, idx):
        removedItem = self.parent.dataStore.removeAtIndex(idx)
        # check for removed layer type, and change field picker states accordingly                
        if removedItem.LayerType == DataLayer.TREES.value:
            self.disableTreeLayerFieldPickers()
        self.updatePickerDataLayerTypes()
        

    def updatePickerDataLayerTypes(self, container = DataLayer):        
        # clear list, then rebuild list, excluding contained types apart from ancillary layers
        self.parent.dlg.pickerLayerType.clear()               
        for layerType in container:
            layerInModel, _ = self.parent.dataStore.containsLayerSourceForType(layerType)
            if not layerInModel or layerType == DataLayer.ANCILLARY_DATA:
                self.parent.dlg.pickerLayerType.addItem(layerType.value)

    def layerTableDoubleClickedEventHandler(self):
        for idx in self.parent.dlg.layerView.selectionModel().selectedIndexes():
            row_number = idx.row()
            column_number = idx.column()            

        # now that we have the row index, get the corresponding layer
        ds = self.parent.dataStore.getItemAtIndex(row_number)
        if ds.GeometryType == SiacGeometryType.POLYGON:
            self.parent.dataStore.setActiveLayer(ds)
        else:
            QtWrapper.showErrorMessage(self.parent.dlg, "Only polygon layers are supported as of now")
        


    def dataSourceLayerListSelectionChanged(self):
        row = None
        column = None

        if self.parent.dlg.layerView.selectionModel().selection().indexes():
            for i in self.parent.dlg.layerView.selectionModel().selection().indexes():
                row, column = i.row(), i.column()
        
        if row is not None:
            # get associated data source
            ds = self.parent.dataStore.getItemAtIndex(row)
            
            self.selectedLayerInLayerView = ds
            
            if DataLayer(ds.LayerType) == DataLayer.ANCILLARY_DATA:
                self.open_ancillary_data_editor_action.setEnabled(True)
            else:
                self.open_ancillary_data_editor_action.setEnabled(False)


        else:
            self.selectedLayerInLayerView = None

    def aboutToShowDataSourcesLayerListContextMenu(self, pos):
        
        row = None

        # make a new menu. show certain options only for certain types
        menu = QMenu()
        setActiveLayerAction = menu.addAction("Set As Active Layer")
        resetActiveLayerAction = menu.addAction("Reset Active Layer")
        setOpenEditorAction = menu.addAction("Open Ancillary Data Editor")
        removeSelectedItemAction = menu.addAction("Remove layer from model")
        menu.addSeparator()
        resolveDsAction = menu.addAction("Resolve data sources")
        

        if self.parent.dlg.layerView.selectionModel().selection().indexes():
            for i in self.parent.dlg.layerView.selectionModel().selection().indexes():
                row, column = i.row(), i.column()
        
        if row is not None:
            # get associated data source
            ds = self.parent.dataStore.getItemAtIndex(row)

            # enable or disable certain actions depending on conditions
            setActiveLayerAction.setEnabled(True if ds.GeometryType == SiacGeometryType.POLYGON else False)
            setOpenEditorAction.setEnabled(True if DataLayer(ds.LayerType) == DataLayer.ANCILLARY_DATA else False) 
            resetActiveLayerAction.setEnabled(True if self.parent.dataStore.getActiveLayer() is not None else False)

        else:
            setActiveLayerAction.setEnabled(False)
            setOpenEditorAction.setEnabled(False) 
            resetActiveLayerAction.setEnabled(False)

        action = menu.exec_(self.parent.dlg.layerView.mapToGlobal(pos))        
        if action == setActiveLayerAction:
            self.parent.dataStore.setActiveLayer(ds)
        if action == setOpenEditorAction:
            if DataLayer(ds.LayerType) == DataLayer.ANCILLARY_DATA:
                self.initAncillaryDataEditor(ds)
        if action == removeSelectedItemAction:
            self.removeItemAtIndexFromListOfLayers(row)
        if action == resetActiveLayerAction:
            self.parent.dataStore.setActiveLayer(None)
        if action == resolveDsAction:
            self.parent.resolveDataSources()
        
    
    # def increaseLogFontSize(self):
    #     cursor = self.parent.dlg.outputTextBox.textCursor()
    #     cFontSize = self.parent.dlg.outputTextBox.fontPointSize()
    #     nFontSize = cFontSize + 1
    #     print(cFontSize)
    #     self.parent.dlg.outputTextBox.selectAll()
    #     self.parent.dlg.outputTextBox.setFontPointSize(nFontSize)
    #     self.parent.dlg.outputTextBox.setTextCursor( cursor )
    
    # def decreaseLogFontSize(self):
    #     cursor = self.parent.dlg.outputTextBox.textCursor()
    #     cFontSize = self.parent.dlg.outputTextBox.fontPointSize()
    #     nFontSize = (cFontSize-1) if (cFontSize-1) > 0 else cFontSize
    #     print(cFontSize)
    #     self.parent.dlg.outputTextBox.selectAll()
    #     self.parent.dlg.outputTextBox.setFontPointSize(nFontSize)
    #     self.parent.dlg.outputTextBox.setTextCursor( cursor )
    



    def aboutToShowExportMenu(self):
            # remove all actions
            self.exportMenu.clear()
            exportDiversityAction = self.exportMenu.addAction("Tree Richness and &Diversity", self.parent.exportRichnessAndDiversityResult)
        
            if SiacToolkitDataType.RICHNESS_AND_DIVERSITY_ASSESSMENT not in self.parent.params[SiacToolkitModule.TCAC].keys() or self.parent.params[SiacToolkitModule.TCAC][SiacToolkitDataType.RICHNESS_AND_DIVERSITY_ASSESSMENT] is None:
                exportDiversityAction.setEnabled(False)
            else:
                exportDiversityAction.setEnabled(True)

    #
    # Initialize/open ancillary data editor
    #
    #
    def initAncillaryDataEditorFromSelectedLayer(self):
        self.initAncillaryDataEditor(self.selectedLayerInLayerView)
    def initAncillaryDataEditor(self, layerDataStoreItem):
        self.nd = Ui_ancillaryLayerDialog(layerPackage=layerDataStoreItem)
        self.nd.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.nd.exec_()
    

    def printToolStatement(self):
        txt = [ "Scheuer, S., Kičić, M., Haase, D., CLEARING HOUSE project, 2023. CLEARING HOUSE Urban Forests as Nature-Based Solutions (UF-NBS) Spatial Impact Assessment and Classification Tool (SIAC). QGIS plugin for the assessment of urban forest conditions and benefits.", "This project has received funding from the European Union’s Horizon 2020 research and innovation programme under grant agreement No 821242." ]
        self.addToToolLog(None, txt)

    def getHelp(self, path):
        # open provided pdf documentation in browser
        url = os.path.join(path, 'documentation', 'documentation.pdf')
        url = 'file:///' + url.replace('\\', '/')
        webbrowser.open(url, new=2)  # open in new tab

    def addToToolLog(self, msgSource : SiacToolkitModule, messages : Iterable[str]) -> None:
        
        if len(messages) == 0:
            return

        currentContent = self.parent.dlg.outputTextBox.toPlainText()
        message = ".\n".join(messages)
        message = '{} {}:\n\n{}.\n\n\n{}'.format( datetime.today().strftime('%d.%m.%Y %H:%M:%S'), '(' + msgSource.value + ')' if msgSource is not None else "", message, currentContent)
        self.parent.dlg.outputTextBox.setPlainText(message)
        
        # switch to output tab
        # self.dlg.tabWidget.setCurrentIndex(2)
    
    def clearToolLog(self):
        self.parent.dlg.outputTextBox.clear()
    
    def saveToolLog(self):
        txtData = self.parent.dlg.outputTextBox.toPlainText()
        SiacExporter.toText(self.parent.dlg, txtData)
