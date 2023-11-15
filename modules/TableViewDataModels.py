from qgis.PyQt.QtCore import Qt, QAbstractTableModel
from qgis.gui import QtCore
from collections import namedtuple

class DataSourceViewModel(QAbstractTableModel):
    
    dataStore = None

    def __init__(self, data=None):
        QAbstractTableModel.__init__(self)
        self.load_data(data)

    def load_data(self, data):
        self.dataStore = data
       
    def data(self, index, role):
        if role == Qt.DisplayRole:
            if index.column() == 1:
                return self.dataStore.getLayers()[index.row()].LayerType 
            elif index.column() == 0:
                return self.dataStore.getLayers()[index.row()].LayerName        

    def rowCount(self, index):
        return len(self.dataStore.getLayers()) 

    def columnCount(self, index):
        return 2

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:            
            if section == 1:
                return "Data Source Type"
            elif section == 0:
                return "Feature Layer Name"

        return super().headerData(section, orientation, role)
        

class AttributeValueMappingViewModel(QAbstractTableModel):
    
    mappingStore = None
    # mappingStore contains Mapping = namedtuple('AttributeValueToEntityMapping', 'AttributeValue EntityType' )
    
    def __init__(self, data=None):
        QAbstractTableModel.__init__(self)
        self.load_data(data)

    def load_data(self, data):
        self.mappingStore = data
       
    def data(self, index, role):
        if role == Qt.DisplayRole:
            if index.column() == 0:
                return '{}'.format(self.mappingStore.getMappings()[index.row()].AttributeValue) 
            elif index.column() == 1:
                return self.mappingStore.getMappings()[index.row()].EntityType.label    

    def rowCount(self, index):
        return len(self.mappingStore.getMappings()) 

    def columnCount(self, index):
        return 2

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:            
            if section == 0:
                return "Attribute Value"
            elif section == 1:
                return "Entity Name"

        return super().headerData(section, orientation, role)