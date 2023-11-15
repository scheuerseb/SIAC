from enum import Enum
from .SiacFields import SiacField
from .SiacEntities import SiacEntity 

# This enumeration defines indicators, e.g., for COIN tool.
# Indicator enumeration values in the form value[x] with x=
# 0 ... field name; 
# 1 ... indicator label; 
# 2 ... average or raw unit (ecosystem service potential/rate per area and unit time); 
# 3 ... sum unit (total ecosystem service benefit for given area and unit time);
# 4 ... conversion factor to be used for converting unit of potential/rate to unit of sum; 1 if same unit (total value is multiplied by conversion factor)
#
#
class SiacIndicator(Enum):    
    TREE_COVER = "TOTAL_TREE_COVER_AREA", "Tree Cover Area", "hectare", "hectare", 1
    CANOPY_COVER_SHARE = SiacField.MORPHOLOGY_TREE_COVER_RELATIVE.value, "Canopy-Covered Area Ratio", "", "", 1
    FOREST_COVER = "TOTAL_FOREST_AREA", SiacEntity.FOREST.label, "m²", "hectare", 0.0001
    TREE_DENSITY = SiacField.MORPHOLOGY_TREE_DENSITY.value, "Tree density", "trees/hectare", "n/a", 1
    TREE_SPECIES_RICHNESS = SiacField.MORPHOLOGY_TREE_SPECIES_RICHNESS.value, "Tree species richness", "number of tree species", "number of tree species", 1
    AVERAGE_CARBON_STORAGE = "AVG_C_STORE", "Carbon Storage", "kg C/m² of tree cover", "Mg C", 0.001
    AVERAGE_CARBON_SEQUESTRATION = "AVG_C_SEQSTR", "Annual Carbon Sequestration", "kg C/m² of tree cover per year", "Mg C per year", 0.001
    AIR_QUALITY_REMOVED_SO2 = "TOT_SO2", "Annual Removal of SO2", "g/m² of tree cover per year", "Mg per year", 0.000001
    AIR_QUALITY_REMOVED_NO2 = "TOT_NO2", "Annual Removal of NO2", "g/m² of tree cover per year", "Mg per year", 0.000001
    AIR_QUALITY_REMOVED_O3 = "TOT_O3", "Annual Removal of O3", "g/m² of tree cover per year", "Mg per year", 0.000001
    AIR_QUALITY_REMOVED_CO = "TOT_CO", "Annual Removal of CO", "g/m² of tree cover per year", "Mg per year", 0.000001
    AIR_QUALITY_REMOVED_PM10 = "TOT_PM10", "Annual Removal of PM10", "g/m² of tree cover per year", "Mg per year", 0.000001
    LOCAL_OLS_IMPACT = "EST_IMPACT", "Local OLS-determined Impact", "", "", 1
    STREET_TREE_DENSITY = "ST_TR_DENS", "Street Tree Density", "trees/km", "trees/km", 1


    def __init__(self, fieldName, label, baseUnit, aggregatedUnit, conversionFactor):
        self.fieldName = fieldName
        self.label = label
        self.baseUnit = baseUnit
        self.convertedUnit = aggregatedUnit
        self.conversionFactor = conversionFactor
