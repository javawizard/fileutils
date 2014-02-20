
from fileutils.interface import BaseFile
from fileutils.mixins import ChildrenMixin
from fileutils.constants import FILE, FOLDER, LINK

class FTPFile(ChildrenMixin, BaseFile):
    pass


