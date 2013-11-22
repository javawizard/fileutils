# This will almost certainly be broken up into multiple modules once this is
# actually done.

from abc import ABCMeta, abstractmethod, abstractproperty
import os


class Hierarchy(object):
    __metaclass__ = ABCMeta
    
    @abstractmethod
    def child(self, *names):
        pass
    
    @abstractproperty
    def parent(self):
        pass
    
    @abstractmethod
    def get_path_components(self, relative_to=None):
        pass
    
    def get_ancestors(self, including_self=False):
        """
        Returns a list of all of the ancestors of this file, with self.parent
        first. If including_self is True, self will be first, self.parent will
        be second, and so on.
        """
        if including_self:
            current = self
        else:
            current = self.parent
        results = []
        while current is not None:
            results.append(current)
            current = current.parent
        return results

    @property
    def ancestors(self):
        """
        A list of all of the ancestors of this file, with self.parent first.
        
        This property simply returns
        :obj:`self.get_ancestors() <get_ancestors>`. Have a look at that
        method if you need to do more complex things like include self as one
        of the returned ancestors.
        """
        return self.get_ancestors()

    def descendant_of(self, other, including_self=False):
        """
        Returns true if this file is a descendant of the specified file. This
        is equivalent to File(other).ancestor_of(self, including_self).
        """
        return other in self.get_ancestors(including_self)

    def ancestor_of(self, other, including_self=False):
        """
        Returns true if this file is an ancestor of the specified file. A file
        is an ancestor of another file if that other file's parent is this
        file, or its parent's parent is this file, and so on.
        
        If including_self is True, the file is considered to be an ancestor of
        itself, i.e. True will be returned in the case that self == other.
        Otherwise, only the file's immediate parent, and its parent's parent,
        and so on are considered to be ancestors.
        """
        return other.descendent_of(self, including_self)

    def get_path(self, relative_to=None, separator=None):
        """
        Gets the path to the file represented by this File object.
        
        If relative_to is specified, the returned path will be a relative path,
        the path of this file relative to the specified one. Otherwise, the
        returned path will be absolute.
        
        If separator (which must be a string) is specified, it will be used as
        the separator to place between path components in the returned path.
        Otherwise, os.path.sep will be used as the separator. 
        """
        if separator is None:
            separator = os.path.sep
        return separator.join(self.get_path_components(relative_to))

    @property
    def path(self):
        """
        The absolute path to the file represented by this File object, in a
        format native to the operating system in use. This pathname can then be
        used with Python's traditional file-related utilities.
        
        This property simply returns self.get_path(). See the documentation for
        that method for more complex ways of creating paths (including
        obtaining relative paths).
        """
        return self.get_path()

    @property
    def path_components(self):
        """
        A property that simply returns
        :obj:`self.get_path_components() <get_path_components>`.
        """
        return self.get_path_components()

    @property
    def name(self):
        """
        The name of this file. For example, File("a", "b", "c").name will be
        "c".
        
        On Unix-based operating systems, File("/").name will be the empty
        string.
        """
        return self.path_components[-1]


class File(Hierarchy):
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


































