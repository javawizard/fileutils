
from fileutils2.interface import Hierarchy, Listable, Readable
from fileutils2.interface import WorkingDirectory, Writable
from fileutils2.mixins import ChildrenMixin
from fileutils2.constants import FILE, FOLDER, LINK
import os.path
import stat

class File(Hierarchy, ChildrenMixin, Listable, Readable, WorkingDirectory,
           Writable):
    def __init__(self, *path_components):
        r"""
        Creates a new file from the specified path components. Each component
        represents the name of a folder or a file. These are internally joined
        as if by os.path.join(*path_components).
        
        It's also possible, although not recommended, to pass a full pathname
        (in the operating system's native format) into File. On Windows, one
        could therefore do File(r"C:\some\file"), and File("/some/file") on
        Linux and other Unix operating systems.
        
        You can also call File(File(...)). This is equivalent to File(...) and
        exists to make it easier for functions to accept either a pathname or
        a File object.
        
        Passing no arguments (i.e. File()) results in a file that refers to the
        working directory as of the time the File instance was constructed.
        
        Pathnames are internally stored in absolute form; as a result, changing
        the working directory after creating a File instance will not change
        the file referred to.
        """
        # If we're passed a File object, use its path
        if path_components and isinstance(path_components[0], File):
            path = path_components[0]._path
        # Join the path components, or use the empty string if there are none
        elif path_components:
            path = os.path.join(*path_components)
        else:
            path = ""
        # Make the pathname absolute
        path = os.path.abspath(path)
        self._path = path
    
    def child(self, *names):
        return File(os.path.join(self.path, *names))

    @property
    def parent(self):
        dirname = os.path.dirname(self._path)
        # I don't remember at the moment how this works on Windows, so cover
        # all the bases until I can test it out
        if dirname is None or dirname == "":
            return None
        f = File(dirname)
        # Linux returns the same file from dirname
        if f == self:
            return None
        return f

    def get_path_components(self, relative_to=None):
        if relative_to is None:
            return self._path.split(os.path.sep)
        else:
            return os.path.relpath(self._path, File(relative_to)._path).split(os.sep)

    @property
    def child_names(self):
        if not self.is_folder:
            return
        return sorted(os.listdir(self._path))
    
    @property
    def type(self):
        try:
            s = os.lstat(self.path)
        except os.error: # File doesn't exist
            return None
        if stat.S_ISREG(s):
            return FILE
        if stat.S_ISDIR(s):
            return FOLDER
        if stat.S_ISLNK(s):
            return LINK
        return "fileutils2.OTHER"

    @property
    def link_target(self):
        """
        Returns the target to which this file, which is expected to be a
        symbolic link, points, as a string. If this file is not a symbolic
        link, None is returned.
        """
        if not self.is_link:
            return None
        return os.readlink(self._path)
    
    def open_for_reading(self):
        return open(self.path, "rb")

    @property
    def size(self):
        """
        The size, in bytes, of this file. This is the number of bytes that the
        file contains; the number of actual bytes of disk space it consumes is
        usually larger.
        
        If this file is actually a folder, the sizes of its child files and
        folders will be recursively summed up and returned. This can take quite
        some time for large folders.
        """
        if self.is_folder:
            return sum(f.size for f in self.children)
        elif self.is_file:
            return os.path.getsize(self.path)
        else: # Broken symbolic link or some other type of file
            return 0

    def change_to(self):
        """
        Sets the current working directory to self.
        
        Since File instances internally store paths in absolute form, other
        File instances will continue to work just fine after this is called.
        
        If you need to restore the working directory at any point, you might
        want to consider using :obj:`self.as_working <as_working>` instead.
        """
        os.chdir(self.path)

    def create_folder(self, ignore_existing=False, recursive=False):
        """
        Creates the folder referred to by this File object. If it already
        exists but is not a folder, an exception will be thrown. If it already
        exists and is a folder, an exception will be thrown if ignore_existing
        is False (the default); if ignore_existing is True, no exception will
        be thrown.
        
        If the to-be-created folder's parent does not exist and recursive is
        False, an exception will be thrown. If recursive is True, the folder's
        parent, its parent's parent, and so on will be created automatically.
        """
        # See if we're already a folder
        if self.is_folder:
            # We are. If ignore_existing is True, then just return.
            if ignore_existing:
                return
            # If it's not, raise an exception. TODO: EAFP
            else:
                raise Exception("The folder %r already exists." % self.path)
        else:
            # We're not a folder. (We don't need to see if we already exist as
            # e.g. a file as the call to os.mkdir will take care of raising an
            # exception for us in such a case.) Now create our parent if it
            # doesn't exist and recursive is True.
            if recursive and self.parent and not self.parent.exists:
                self.parent.create_folder(recursive=True)
            # Now turn ourselves into a folder.
            os.mkdir(self.path)

    def delete(self, contents=False, ignore_missing=False):
        """
        Deletes this file or folder, recursively deleting children if
        necessary.
        
        The contents parameter has no effect, and is present for backward
        compatibility.
        
        If the file does not exist and ignore_missing is False, an exception
        will be thrown. If the file does not exist but ignore_missing is True,
        this function simply does nothing.
        
        Note that symbolic links are never recursed into, and are instead
        themselves removed.
        """
        if not self.exists:
            if not ignore_missing:
                raise Exception("This file does not exist.")
        elif self.is_folder and not self.is_link:
            for child in self.children:
                child.delete()
            os.rmdir(self.path)
        else:
            os.remove(self._path)

    def link_to(self, other):
        """
        Creates this file as a symbolic link pointing to other, which can be
        a pathname or a File object. Note that if it's a pathname, a symbolic
        link will be created with the exact path specified; it will therefore
        be absolute if the path is absolute or relative (to the link itself) if
        the path is relative. If a File object, however, is used, the symbolic
        link will always be absolute.
        """
        if isinstance(other, File):
            os.symlink(other.path, self._path)
        else:
            os.symlink(other, self._path)
    
    def open_for_writing(self, append=False):
        if append:
            return open(self.path, "ab")
        else:
            return open(self.path, "wb")

    def __str__(self):
        return "fileutils2.File(%r)" % self._path
    
    __repr__ = __str__
    
    # Use __cmp__ instead of the rich comparison operators for brevity
    def __cmp__(self, other):
        if not isinstance(other, File):
            return NotImplemented
        return cmp(os.path.normcase(self.path), os.path.normcase(other.path))
    
    def __hash__(self):
        return hash(os.path.normcase(self.path))
    
    def __nonzero__(self):
        """
        Returns True. File objects are always true values; to test for their
        existence, use self.exists instead.
        """
        return True


