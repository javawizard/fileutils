
from fileutils.interface import Listable, Readable, Writable, Hierarchy
from fileutils.interface import ReadWrite
from fileutils.mixins import ChildrenMixin
from fileutils.constants import FILE, FOLDER, LINK

class FTPFile(ChildrenMixin, Listable, Readable, Writable, Hierarchy,
              ReadWrite):
    pass


