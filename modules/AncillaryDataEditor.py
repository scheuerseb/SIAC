from ..modules.toolkitData.SiacEntities import SiacEntity
from ..modules.toolkitData.AttributeValueMapping import AttributeValueMapping, SiacLayerMappingType
from ..modules.SiacFoundation import LayerHelper
from ..modules.QtUiWrapper import QtWrapper
from ..modules.toolkitData.SiacDataStoreLayerSource import SiacDataStoreLayerSource

from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar, QMenu, QHeaderView, QFileDialog

class AncillaryDataEditor():

    layer = None
    dlg = None

    def __init__(self, parentDlg, layerPackage : SiacDataStoreLayerSource) -> None:
        self.dlg = parentDlg
        self.layer = layerPackage # datastorelayersource

        print(self.layer.LayerSource.name())
        print(self.layer.LayerMapping.getMappings())

        self.dlg.setWindowTitle('Edit Ancillary Data For {}'.format(self.layer.LayerName))

        # by default, hide frameLayer
        self.dlg.frameLayer.setVisible(False)

        # populate all pickers 
        # add all mapping types to picker
        for t in SiacLayerMappingType:
            self.dlg.pickerMappingType.addItem(t.value)
        
        # populate fieldname pickers
        for fieldName in self.layer.LayerSource.fields().names():
            self.dlg.pickerFieldName.addItem(fieldName)

        # populate entity pickers
        for entity in SiacEntity:
            self.dlg.pickerEntityTypeByAttribute.addItem(entity.label)
            self.dlg.pickerEntityTypeByLayer.addItem(entity.label)
        # by default, deselect values from pickers
        self.dlg.pickerEntityTypeByAttribute.setCurrentIndex(-1)
        self.dlg.pickerEntityTypeByLayer.setCurrentIndex(-1)
                        
        # set pickers according to layer properties        
        # set correct item according to current mapping value
        self.dlg.pickerMappingType.setCurrentText(self.layer.LayerMapping.MappingType.value)
        self.mappingTypeChanged()

        # set current field, if any
        if self.layer.LayerMapping.FieldName is not None:
            self.dlg.pickerFieldName.setCurrentText(self.layer.LayerMapping.FieldName)
            self.updateUniqueValues(self.layer.LayerMapping.FieldName)
        else:
            self.dlg.pickerFieldName.setCurrentIndex(-1)

        # update layer entity type, if applicable
        if self.layer.LayerMapping.LayerEntityType is None:
            self.dlg.pickerEntityTypeByLayer.setCurrentIndex(-1)
        else:
            self.dlg.pickerEntityTypeByLayer.setCurrentText(self.layer.LayerMapping.LayerEntityType.label)


        # init attribMappingView
        self.dlg.attribMappingView.setModel(self.layer.LayerMapping.getViewModel())
        self.dlg.attribMappingView.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layer.LayerMapping.emitViewModelChange()

        # connect event handlers etc.
        self.dlg.pickerMappingType.currentTextChanged.connect(self.mappingTypeChanged)
        self.dlg.btnAddMapping.clicked.connect(self.addMappingToLayer)
        self.dlg.btnRemoveMapping.clicked.connect(self.removeMappingFromLayer)
        self.dlg.pickerFieldName.currentTextChanged.connect(self.pickerFieldNameChanged)
        self.dlg.pickerEntityTypeByLayer.currentTextChanged.connect(self.pickerEntityTypeByLayerChanged)


    def addMappingToLayer(self):
        
        if self.dlg.pickerFieldValue.currentIndex() == -1 or self.dlg.pickerEntityTypeByAttribute.currentIndex() == -1:
            QtWrapper.showErrorMessage(self.dlg, "Select an attribute value and the corresponding entity type")
            return

        currentAttributeValue = self.dlg.pickerFieldValue.currentData()
        currentEntityType = SiacEntity.from_label(self.dlg.pickerEntityTypeByAttribute.currentText())
        self.layer.LayerMapping.addMapping(currentAttributeValue, currentEntityType)

    def removeMappingFromLayer(self):
        selectedRows = self.dlg.attribMappingView.selectedIndexes()
        rowsToRemove = []
        for r in selectedRows:
            # r is a QModelIndex object            
            # r.row() gives the index to remove
            if r.row() not in rowsToRemove:
                rowsToRemove.append(r.row())

        if len(rowsToRemove) > 0:
            for idx in reversed(rowsToRemove):
                self.layer.LayerMapping.removeAtIndex(idx)
            
        self.dlg.attribMappingView.clearSelection()


    # update ui after mapping type to show correct frames, and update layer accordingly
    def mappingTypeChanged(self):
        selectedMappingType = SiacLayerMappingType(self.dlg.pickerMappingType.currentText())
        self.dlg.frameMapping.setVisible(True if selectedMappingType == SiacLayerMappingType.BY_ATTRIBUTE else False) 
        self.dlg.frameLayer.setVisible(False if selectedMappingType == SiacLayerMappingType.BY_ATTRIBUTE else True)
        # after taking care of UI, now also update layer mapping type
        self.layer.LayerMapping.MappingType = selectedMappingType

    def updateUniqueValues(self, fieldName):
        # delete old unique values, if any
        self.dlg.pickerFieldValue.clear()
        uniqueVals = LayerHelper.getUniqueValuesForField(self.layer.LayerSource, fieldName)
        # insert unique values into picker for selection
        for uval in uniqueVals:
            self.dlg.pickerFieldValue.addItem('{}'.format(uval), userData=uval)

    # update unique values for selection from selected field, and update layer accordingly that this field is used
    def pickerFieldNameChanged(self):        
        selectedFieldName = self.dlg.pickerFieldName.currentText()                
        # update layer to use selected field
        self.layer.LayerMapping.FieldName = selectedFieldName
        # determine unique values for selected field
        self.updateUniqueValues(selectedFieldName)

    # update layer entity type if changed
    def pickerEntityTypeByLayerChanged(self):
        currentLayerEntityType = SiacEntity.from_label(self.dlg.pickerEntityTypeByLayer.currentText())
        # update layer entity type
        self.layer.LayerMapping.LayerEntityType = currentLayerEntityType
