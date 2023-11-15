from ..TableViewDataModels import AttributeValueMappingViewModel
from ..toolkitData.SiacEntities import SiacEntity

from enum import Enum
from typing import Iterable

# This class is used to map attributes of a field to entites, e.g., land-use to specific classes
class AttributeValueToEntityMapping():

    _attributeValue = None
    _entityType = None

    def __init__(self, newAttributeValue : any, newEntityType : SiacEntity) -> None:
        self._attributeValue = newAttributeValue
        self._entityType = newEntityType

    @property
    def AttributeValue(self) -> any:
        return self._attributeValue
    @property
    def EntityType(self) -> SiacEntity:
        return self._entityType


class SiacLayerMappingType(Enum):
    BY_ATTRIBUTE = "Entities from attribute values"
    BY_LAYER = "Entities are the layer features"




class AttributeValueMapping():

    _FieldName = None
    _MappingType = None
    _LayerEntityType = None
    _Id = None

    layer = None
    attribsViewModel = None
    attribsToEntitiesMapping : Iterable[AttributeValueToEntityMapping] = None

    def __init__(self, id : str) -> None:
        self._Id = id
        self.attribsToEntitiesMapping = []
        self.MappingType = SiacLayerMappingType.BY_ATTRIBUTE
        self.attribsViewModel = AttributeValueMappingViewModel(self)

    def getViewModel(self):
        return self.attribsViewModel

    @property
    def MappingId(self):
        return self._Id
    
    @property
    def FieldName(self):
        return self._FieldName
    @FieldName.setter
    def FieldName(self, value):
        self._FieldName = value

    @property
    def MappingType(self) -> SiacLayerMappingType:
        return self._MappingType
    @MappingType.setter
    def MappingType(self, value : SiacLayerMappingType):
        self._MappingType = value

    @property
    def LayerEntityType(self) -> SiacEntity: 
        return self._LayerEntityType
    @LayerEntityType.setter
    def LayerEntityType(self, value : SiacEntity):
        self._LayerEntityType = value

    def representsEntityType(self, entityType : SiacEntity) -> bool:
        if self.MappingType == SiacLayerMappingType.BY_LAYER:
            return True if self.LayerEntityType == entityType else False
        
        elif self.MappingType == SiacLayerMappingType.BY_ATTRIBUTE:
            for mapping in self.getMappings():
                if mapping.EntityType == entityType:
                    return True        
            return False        

    def getMappings(self) -> Iterable[AttributeValueToEntityMapping]:
        return self.attribsToEntitiesMapping
    
    def setMappings(self, mappings : Iterable[AttributeValueToEntityMapping]) -> None:
        self.attribsToEntitiesMapping = mappings
    
    def getMappingsForEntityType(self, entityType : SiacEntity) -> Iterable[AttributeValueToEntityMapping]:        
        result = []
        for mapping in self.getMappings():
            if mapping.EntityType == entityType:
                result.append(mapping)
        return result

    def addMapping(self, attributeValue : object, entityType : SiacEntity) -> None:
        newMapping = AttributeValueToEntityMapping(attributeValue, entityType)     
        self.attribsToEntitiesMapping.append(newMapping)
        self.emitViewModelChange()

    def removeAtIndex(self, idx):        
        removedItem = self.attribsToEntitiesMapping.pop(idx)
        self.emitViewModelChange()
        return removedItem

    def emitViewModelChange(self):
        self.attribsViewModel.layoutChanged.emit()   


class SerializableAttributeValueMappingDefinition():

    fieldName : str = None
    mappingType : SiacLayerMappingType = None
    layerEntityType : SiacEntity = None
    attribsToEntitiesMapping : Iterable[AttributeValueToEntityMapping] = []

    def __init__(self, sourceObj : AttributeValueMapping ) -> None:
        self.attribsToEntitiesMapping = sourceObj.getMappings()
        self.fieldName = sourceObj.FieldName
        self.layerEntityType = sourceObj.LayerEntityType
        self.mappingType = sourceObj.MappingType

