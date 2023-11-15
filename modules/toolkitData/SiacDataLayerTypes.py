from enum import Enum


# This enumeration is used to define layer data types, i.e., content of layers
#
#

class DataLayer(Enum):

    TREES = "Tree cadastre"    
    CLASSIFIED_TREES = "Classified tree cadastral data"
    BUILDINGS = "Buildings"
    STREETS = "Street centerlines"
    MORPHOLOGY_STREETS = "Street Morphology"
    TREES_ENVELOPES = "Tree envelopes"
    TREE_COVER_MBR = "Tree Cover MBR"
    TREE_COVER_DISSOLVED_MBR = "Tree Cover Dissolved MBR"
    TREE_COVER = "Tree Cover"    
    ANCILLARY_DATA = "Ancillary Data Layer"
    MORPHOLOGY_PLOTS = "Plots"
    TOPOLOGY_TREES_NEAR_STREETS = "Nearest street feature to trees"
    TOPOLOGY_TREES_NEAR_BUILDINGS = "Nearest building feature to trees"
    TOPOLOGY_TREES_NEAR_ENTITY = "Nearest feature to trees"
    CONNECTIVITY_BASE_LAYER = "Connectivity Base Layer"
    CONNECTIVITY_EDGES = "Connectivity Edges"
    CONNECTIVITY_NODES = "Connectivity Nodes"
    CONNECTIVITY_NEAREST_NEIGHBOURS = "Nearest neighbours network"
    SITA_SAMPLED_LOCATIONS = "SITA Random Locations Sample"
