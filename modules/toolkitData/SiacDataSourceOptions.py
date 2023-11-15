class DataSourceOptions:
    _Crs = None

    @property
    def Crs(self):
        return self._Crs
    @Crs.setter
    def Crs(self, value):
        self._Crs = value

ProjectDataSourceOptions = DataSourceOptions()
