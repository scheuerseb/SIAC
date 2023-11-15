from enum import Enum, EnumMeta

# This enumeration is used to internally refer to field names within layer attribute tables.
#
#


class SiacField(Enum):
    RELEVANT_FEATURE_AREA = "ENTITY_AREA"
    FRUIT_TREE_COUNT = "FRUIT_TR_COUNT"
    FRUIT_TREE_SHARE = "FRUIT_TR_SHARE"
    TREE_SPECIES = "TREE_SPECIES"
    TREE_SPECIES_COUNTS = "TREE_SPECIES_CNT"
    CONTAINED_TREE_IDS = "TREE_IDS"
    TREE_CLASSIFICATION = "TREE_CLASS"
    SOLITARY_TREE_CLASSIFICATION = "S_TREE_CLASS"
    SIAC_ID = "SIACID"
    UID_TREE = "SIAC_TRID"
    UID_CANOPY = "SIAC_CCID"
    UID_CONNECT = "SIAC_CONNECTID"
    UID_STREETSEGMENT = "SIAC_STRID"
    UID_BUILDING = "SIAC_BLDID"
    ESS_MEDIATION = "ESS_K"

    
    TOPOLOGY_DISTANCE_TO_STREET = "DIST_STR"
    TOPOLOGY_DISTANCE_TO_BUILDING = "DIST_BLDG"
    TOPOLOGY_ADJACENCY_TO_STREET = "NEAR_STR"
    TOPOLOGY_ADJACENCY_TO_BUILDING = "NEAR_BLDG"
    TOPOLOGY_CONTAINMENT_IN_STREET = "IN_STREET"    
    TOPOLOGY_IN_TREE_COUNT = "TR_CNT_IN"
    TOPOLOGY_NEAR_TREE_COUNT = "TR_CNT_NEAR"
    
    
    CONNECTIVITY_LINK_OBSTRUCTED = "LINK_OBSTR"         # assessed by TOPOMOD as intersect of building and shortest line
    CONNECTIVITY_LINK_OUT_OF_RANGE = "LINK_RANGE"       # assessed by TOPOMOD as function of user-specified connectivity threshold
    CONNECTIVITY_LINK_VALID = "LINK_VALID"
    CONNECTIVITY_CANOPY_CPL = "PATCH_CPL"               # Characteristic path length for a given closed canopy cover to unobstructed canopies, from X nearest canopies
    CONNECTIVITY_CANOPY_LNK = "PATCH_LNK"               # Number of links (connections) for a given closed canopy cover to unobstructed canopies, from X nearest canopies
    CONNECTIVITY_CANOPY_CAPACITY = "PATCH_A"            # Capacity of the canopy patch, here, tree cover area 
    CONNECTIVITY_CLOSENESS_CENTRALITY = "PATCH_CCE"     # closeness centrality of patch i.e. avg distance of patch in components
    CONNECTIVITY_ECCENTRICITY = "PATCH_EC"              # eccentricity of patch i.e. max distance to patch in components    
    CONNECTIVITY_DEGREE_CENTRALITY = "PATCH_DEG"        # degree of centrality
    CONNECTIVITY_BETWEENNESS_CENTRALITY = "PATCH_BETW"  # betweenness centrality
    CONNECTIVITY_COMPONENT_ID = "COMPONENT_ID"          # Feature id of the corresponding component
    CONNECTIVITY_COMPONENT_NK = "COMPONENT_NK"          # Number of patches in the component
    CONNECTIVITY_COMPONENT_CAPACITY = "COMPONENT_A"     # Capacity of the component, i.e., sum of capacities of contained patches
    CONNECTIVITY_COMPONENT_DIAMETER = "COMPONENT_GD"    # graph diameter of each component, i.e., max eccentricity
    CONNECTIVITY_IS_BRIDGE = "IS_BRIDGE"
    CONNECTIVITY_IS_ARTICULATION_POINT = "IS_ARTICULATE"
    
    CLASS_TREED_AREA = "IS_TREEDAREA"                   # Class treed area
    CLASS_FOREST = "IS_FOREST"                          # Class forest area 

    
    MORPHOLOGY_TREE_COUNT = "TREE_COUNT"
    MORPHOLOGY_TREE_COVER_ENTITY_COUNT = "TREE_COVER_COUNT"
    MORPHOLOGY_TREE_COVER_TOTAL = "TREE_COVER_AREA"
    MORPHOLOGY_TREE_COVER_RELATIVE = "TREE_COVER_SHARE"
    MORPHOLOGY_TREE_DENSITY = "TREE_DENS"
    MORPHOLOGY_TREE_SPECIES_RICHNESS = "TREE_RICHN"
    MORPHOLOGY_CONTAINS_FRUIT_TREES = "HAS_FRUIT_TR"
    MORPHOLOGY_BUILDING_TOTAL = "BUILDING_AREA"
    MORPHOLOGY_BUILDING_RELATIVE = "BUILDING_SHARE"
    MORPHOLOGY_STREET_TOTAL = "STREET_AREA"
    MORPHOLOGY_STREET_RELATIVE = "STREET_SHARE"
    MORPHOLOGY_IMPERVIOUS_AREA_TOTAL = "IMPERV_AREA"
    MORPHOLOGY_IMPERVIOUS_AREA_RELATIVE = "IMPERV_SHARE"
    
    
    MAPTOOLS_PERIMETER_DIAMETER = "DIAMETER"
    
    OLS_DEPENDENT_MEAN = "MEAN_VAL"
    OLS_DEPENDENT_MIN = "MIN_VAL"
    OLS_DEPENDENT_MAX = "MAX_VAL"
    OLS_DEPENDENT_STD = "STD_VAL"