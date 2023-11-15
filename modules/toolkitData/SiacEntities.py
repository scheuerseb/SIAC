from enum import Enum

# This enum defines values for various entity types, including field names to be used for assessments

class SiacEntity(Enum):

    FOREST = "FOREST", "FOREST"
    URBAN_GREEN_SPACE = "URBAN GREEN SPACE", "UGS"
    WATER_BODIES = "WATER BODIES", "WATER"
    AMENITY_FEATURES_GENERAL = "AMENITY FEATURES", "AMENITY_G"
    
    def __init__(self, label, fieldPrefix):
        self.label = label
        self.fieldPrefix = fieldPrefix
    
    def getTotalCoverFieldName(self):
        return '{}_AREA'.format(self.fieldPrefix)
    def getRelativeCoverFieldName(self):
        return '{}_SHARE'.format(self.fieldPrefix)
    def getContainmentFieldName(self):
        return 'HAS_{}'.format(self.fieldPrefix)
    def getOtherEntityIsContainedFieldName(self):
        return 'IN_{}'.format(self.fieldPrefix)
    def getDistanceToEntityFieldName(self):
        return 'DIST_{}'.format(self.fieldPrefix)
    def getAdjacencyToEntityFieldName(self):
        return 'NEAR_{}'.format(self.fieldPrefix)
    

    @classmethod
    def from_label(cls, description):
        for item in cls:
            if item.value[0] == description:
                return item
        raise ValueError("%r is not a valid %s description" % (description, cls.__name__))