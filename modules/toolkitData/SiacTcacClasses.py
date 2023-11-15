from enum import Enum

# This Enumeration defines the classes for TCAC to express spatial configuration and patterns of trees  
#
#

class TreePatternConfiguration(Enum):
    UNDEFINED = "undefined"
    SOLITARY = "solitary"

    SOLITARY_SINGLE_TREE = "solitary-single-tree"    
    SOLITARY_PAIR = "solitary-tree-paired"
    SOLITARY_POTENTIAL_ROW = "solitary-potential-row"
    SOLITARY_OTHER_GROUPING = "solitary-other-grouping"

    CLUSTERED_GROUPING = "clustered-grouping"
    DISPERSED_OR_REGULAR_GROUPING = "dispersed-or-regular-grouping"
    CLUSTERED_LINEAR_GROUPING = "clustered-linear-grouping"
    DISPERSED_OR_REGULAR_LINEAR_GROUPING = "dispersed-or-regular-linear-grouping"
