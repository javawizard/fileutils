
from abc import ABCMeta, abstractmethod, abstractproperty
import os.path
from fileutils2.constants import FILE, FOLDER, LINK
import hashlib

class Hierarchy(object):
    __metaclass__ = ABCMeta
    
    @abstractmethod
    def child(self, *names):
        """
        Returns a file object representing the child of this file with the
        specified name. If multiple names are present, they will be joined
        together. If no names are present, self will be returned.
        
        If any names are absolute, all names before them (and self) will be
        discarded. Relative names (like "..") are also allowed. If you want a
        method that guarantees that the result is a child of self, use
        self.safe_child(...).
        
        This method is analogous to
        :obj:`os.path.join(self.path, *names) <os.path.join>`.
        """
    
    @abstractproperty
    def parent(self):
        """
        Returns a file representing the parent of this file. If this file has
        no parent (for example, if it's "/" on Unix-based operating systems or
        a drive letter on Windows), None will be returned.
        """
    
    @abstractmethod
    def get_path_components(self, relative_to=None):
        """
        Returns a list of the components in this file's path, including (on
        POSIX-compliant systems) an empty leading component for absolute paths.
        
        If relative_to is specified, the returned set of components will
        represent a relative path, the path of this file relative to the
        specified one. Otherwise, the returned components will represent an
        absolute path.
        """
    
    def same_as(self, other):
        # True if self' and other's paths mean the same thing, false if they
        # don't. Mainly useful for URLs, where the idea is that, given:
        #
        # a = URL("http://foo/a")
        # b = URL("http://foo/a/")
        # 
        # a == b is False, but a.same_as(b) is True. Can be overridden by
        # subclasses as needed to implement this sort of logic.
        if type(self) != type(other):
            return False
        return self.path_components == other.path_components
    
    def sibling(self, *names):
        return self.parent.child(*names)
    
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
        for ancestor in self.get_ancestors(including_self):
            if other.same_as(ancestor):
                return True
        return False

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
        return other.descendant_of(self, including_self)

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


class Readable(object):
    __metaclass__ = ABCMeta
    
    _default_block_size = 16384
    
    @abstractproperty
    def type(self):
        """
        The type of this file. This can be one of FILE, FOLDER, or LINK (I
        don't yet have constants for block/character special devices; those
        will come soon.) If the file does not exist, this should be None.
        """
        pass
    
    @abstractproperty
    def link_target(self):
        pass
    
    @abstractmethod
    def open_for_reading(self):
        # Should open in "rb" mode
        pass

    @abstractproperty
    def size(self):
        pass
    
    @property
    def exists(self):
        return self.type is not None

    @property
    def valid(self):
        return self.dereference().exists
    
    @property
    def is_broken(self):
        return self.is_link and not self.dereference().exists
    
    @property
    def is_file(self):
        return self.dereference().type is FILE
    
    @property
    def is_folder(self):
        return self.dereference().type is FOLDER
    
    @property
    def is_directory(self):
        return self.is_folder
    
    @property
    def is_link(self):
        return self.type is LINK
    
    def check_folder(self):
        """
        Checks to see whether this File refers to a folder. If it doesn't, an
        exception will be thrown.
        """
        if not self.is_folder:
            raise Exception('"%s" does not exist or is not a directory' % self._path)
    
    def check_file(self):
        """
        Checks to see whether this File refers to a file. If it doesn't, an
        exception will be thrown.
        """
        if not self.is_file:
            raise Exception('"%s" does not exist or is not a file' % self._path)
    
    def copy_to(self, other, overwrite=False):
        """
        Copies the contents of this file to the specified File object or
        pathname. An exception will be thrown if the specified file already
        exists and overwrite is False.
        
        This `does not currently work for folders
        <https://github.com/javawizard/fileutils/issues/1>`_;
        I hope to add this ability in the near future.
        """
        # If self.is_folder is True, requires isinstance(self, Listable) and
        # isinstance(other, Hierarchy) when we implement support for folders.
        # Requires isinstance(other, Writable) always.
        self.check_file()
        # TODO: Use (and catch or pass on) proper exceptions here, EAFP style
        if other.exists and not overwrite:
            raise Exception("%r already exists" % other)
        with other.open_for_writing() as write_to:
            for block in self.read_blocks():
                write_to.write(block)

    def copy_into(self, other, overwrite=False):
        """
        Copies this file to an identically named file inside the specified
        folder. This is just shorthand for self.copy_to(other.child(self.name))
        which, from experience, seems to be by far the most common use case for
        the copy_to function.
        """
        self.copy_to(other.child(self.name), overwrite)

    def dereference(self, recursive=False):
        """
        Dereference the symbolic link represented by this file and return a
        File object pointing to the symbolic link's referent.
        
        If recursive is False, a File object pointing directly to the referent
        will be returned. If recursive is True, the referent itself will be
        recursively dereferenced, and the returned File will be guaranteed not
        to be a link.
        
        If this file is not a symbolic link, self will be returned.
        """
        if not self.is_link:
            return self
        # Resolve the link relative to its parent in case it points to a
        # relative path
        target = self.parent.child(self.link_target)
        if recursive:
            return target.dereference(recursive=True)
        else:
            return target

    def hash(self, algorithm=hashlib.md5, return_hex=True):
        """
        Compute the hash of this file and return it, as a hexidecimal string.
        
        The default algorithm is md5. An alternate constructor from hashlib
        can be passed as the algorithm parameter; file.hash(hashlib.sha1)
        would, for example, compute the SHA-1 hash instead.
        
        If return_hex is False (it defaults to True), the hash object itself
        will be returned instead of the return value of its hexdigest() method.
        One can use this to access the binary hash instead.
        """
        hasher = algorithm()
        for block in self.read_blocks():
            hasher.update(block)
        if return_hex:
            hasher = hasher.hexdigest()
        return hasher
    
    def read_blocks(self, block_size=None):
        """
        A generator that yields successive blocks of data from this file. Each
        block will be no larger than block_size bytes, which defaults to 16384.
        This is useful when reading/processing files larger than would
        otherwise fit into memory.
        
        One could implement, for example, a copy function thus::
        
            with target.open("wb") as target_stream:
                for block in source.read_blocks():
                    target_stream.write(block)
        """
        if block_size is None:
            block_size = self._default_block_size
        with self.open_for_reading() as f:
            data = f.read(block_size)
            while data:
                yield data
                data = f.read(block_size)

    def read(self):
        """
        Read the contents of this file and return them as a string. This is
        usually a bad idea if the file in question is large, as the entire
        contents of the file will be loaded into memory.
        """
        with self.open_for_reading() as f:
            return f.read()


class Listable(Readable):
    __metaclass__ = ABCMeta
    
    @abstractproperty
    def children(self):
        pass
    
    @abstractproperty
    def child_names(self):
        pass


class WorkingDirectory(object):
    __metaclass__ = ABCMeta
    
    @abstractmethod
    def change_to(self):
        pass
    
    def cd(self):
        self.change_to()
    
    @property
    def as_working(self):
        """
        A property that returns a context manager. This context manager sets
        the working directory to self upon being entered and restores it to
        what it previously was upon being exited. One can use this to replace
        something like::
        
            old_dir = File()
            new_dir.cd()
            try:
                ...stuff...
            finally:
                old_dir.cd()
        
        with the much nicer::
        
            with new_dir.as_working:
                ...stuff...
        
        and get exactly the same effect.
        
        The context manager's __enter__ returns self (this file), so you can
        also use an "as" clause on the with statement to get access to the
        file in case you haven't got it stored in a variable anywhere.
        """
        return _AsWorking(self)


class _AsWorking(object):
    """
    The class of the context managers returned from
    WorkingDirectory.as_working. See that method's docstring for more
    information on what this class does.
    """
    def __init__(self, folder):
        self.folder = folder
    
    def __enter__(self):
        self.old = type(self.folder)()
        self.folder.cd()
        return self.folder
    
    def __exit__(self, *args):
        self.old.cd()


class Writable(object):
    __metaclass__ = ABCMeta
    
    @abstractmethod
    def create_folder(self, ignore_existing=False, recursive=False):
        pass
    
    @abstractmethod
    def delete(self, ignore_missing=False):
        pass
    
    @abstractmethod
    def link_to(self, target):
        pass
    
    @abstractmethod
    def open_for_writing(self, append=False):
        pass

#    def append(self, data):
#        """
#        Append the specified data to the end of this file.
#        """
#        with open(self.path, "ab") as f:
#            f.write(data)

    def write(self, data, binary=True):
        """
        Overwrite this file with the specified data. After this is called,
        self.size will be equal to len(data), and self.read() will be equal to
        data. If you want to append data instead, use self.append().
        
        If binary is True (the default), the file will be written
        byte-for-byte. If it's False, the file will be written in text mode. 
        """
        with open(self.path, "wb") as f:
            f.write(data)
