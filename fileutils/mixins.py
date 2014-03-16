
from fileutils.interface import BaseFile, MountDevice

class ChildrenMixin(BaseFile):
    @property
    def children(self):
        """
        A list of all of the children of this file, as a list of File objects.
        If this file is not a folder, the value of this property is None.
        """
        child_names = self.child_names
        if child_names is None:
            return None
        return [self.child(p) for p in child_names]


class DefaultMountDevice(MountDevice):
    def __init__(self, location, device, subpath):
        self._location = location
        self._device = device
        self._subpath = subpath
    
    @property
    def location(self):
        return self._location
    
    @property
    def device(self):
        return self._device
    
    @property
    def subpath(self):
        return self._subpath
    
    def __str__(self):
        if self.subpath != '/':
            return "<DefaultMountDevice {0!r}, subpath {1!r}>".format(self.device, self.subpath)
        else:
            return "<DefaultMountDevice {0!r}>".format(self.device)
    
    __repr__ = __str__
