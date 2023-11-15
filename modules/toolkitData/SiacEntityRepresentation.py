from .SiacDataStoreLayerSource import SiacDataStoreLayerSource
from .SiacEntities import SiacEntity
from ..SiacFoundation import CachedLayerItem


class SiacEntityRepresentation:

    _Layer = None
    _Cache = None
    _FieldIndexTotal = None
    _FieldIndexRelative = None
    _FieldIndexContainment = None
    _EntityType = None

    def __init__(self, cType : SiacEntity) -> None:
        self._EntityType = cType

    @property
    def EntityType(self) -> SiacEntity:
        return self._EntityType

    @property
    def Layer(self) -> SiacDataStoreLayerSource:
        return self._Layer
    @Layer.setter
    def Layer(self, value : SiacDataStoreLayerSource) -> None:
        self._Layer = value

    @property
    def Cache(self) -> CachedLayerItem:
        return self._Cache
    @Cache.setter
    def Cache(self, value : CachedLayerItem):
        self._Cache = value

    @property
    def FieldIndexTotal(self) -> int:
        return self._FieldIndexTotal
    @FieldIndexTotal.setter
    def FieldIndexTotal(self, value : int):
        self._FieldIndexTotal = value

    @property
    def FieldIndexRelative(self) -> int:
        return self._FieldIndexRelative
    @FieldIndexRelative.setter
    def FieldIndexRelative(self, value : int):
        self._FieldIndexRelative = value

    @property
    def FieldIndexContainment(self) -> int:
        return self._FieldIndexContainment
    @FieldIndexContainment.setter
    def FieldIndexContainment(self, value : int):
        self._FieldIndexContainment = value
    