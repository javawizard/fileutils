
from fileutils.interface import Listable, Readable

class ChildrenMixin(Listable, Readable):
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


