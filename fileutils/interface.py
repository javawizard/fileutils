"""
Abstract classes.
"""

from abc import ABCMeta, abstractmethod, abstractproperty
import os.path
from fileutils.constants import FILE, FOLDER, LINK, YIELD, RECURSE
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
        """
        Returns True if this file represents the same file as the specified
        one, False otherwise.
        
        This is usually the same as self == other, but URL implements this
        differently: a URL with a trailing slash and a URL without are treated
        as the same by same_as but different by ==.
        
        The default implementation returns True if self.path_components ==
        other.path_components and type(self) == type(other), or False otherwise.
         
        """
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
    
    def safe_child(self, *names):
        """
        Same as self.child(*names), but checks that the resulting file is a
        descendant of self. If it's not, an exception will be thrown. This
        allows unsanitized paths to be used without fear that things like ".."
        will be used to escape the confines of self.
        
        The pathname may contain occurrences of ".." so long as they do not
        escape self. For example, "a/b/../c" is perfectly fine, but "a/../.."
        is not.
        """
        child = self.child(*names)
        if not self.ancestor_of(child):
            raise ValueError("Names %r escape the parent %r" % (names, self))
        return child
    
    def __div__(self, other):
        """
        An absolutely pointless and unnecessary alias for self.child(other)
        that exists solely because I was overly bored one night while working
        on fileutils.
        """
        return self.child(other)

    def sibling(self, *names):
        """
        Returns a File object representing the sibling of this file with the
        specified name. This is equivalent to self.parent.child(name).
        """
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
        is equivalent to other.ancestor_of(self, including_self).
        """
        for ancestor in self.get_ancestors(including_self):
            if other.same_as(ancestor):
                return True
        return False

    def ancestor_of(self, other, including_self=False):
        """
        Returns true if this file is an ancestor of the specified file. A file
        is an ancestor of another file if that other file's parent is (as
        decided by :obj:`~same_as`) this file, or its parent's parent is this
        file, and so on.
        
        If including_self is True, the file is considered to be an ancestor of
        itself, i.e. True will be returned in the case that self.same_as(other).
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
        The absolute path to the file represented by this file object, in a
        format native to the type of file in use. For instances of
        fileutils.local.File, this pathname can be used with Python's
        traditional file-related utilities.
        
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
        """
        Returns the target to which this file, which is expected to be a
        symbolic link, points, as a string. If this file is not a symbolic
        link, None is returned.
        
        Subclasses (such as URL) without a well-defined notion of symbolic
        links are free to interpret this as they wish; URL, for example,
        presents as a link any URL which sends back an HTTP redirect.
        """
    
    @abstractmethod
    def open_for_reading(self):
        """
        Open this file for reading in binary mode and return a Python file-like
        object from which this file's contents can be read.
        """
        # Should open in "rb" mode

    @abstractproperty
    def size(self):
        """
        The size, in bytes, of this file. This is the number of bytes that the
        file contains; the number of actual bytes of disk space it consumes is
        usually larger.
        
        If this file is actually a folder, the sizes of its child files and
        folders will be recursively summed up and returned. This can take quite
        some time for large folders.
        
        This is the same as len(self).
        """
    
    @property
    def exists(self):
        """
        True if this file/folder exists, False if it doesn't. This will be True
        even for broken symbolic links; use self.valid if you want an
        alternative that returns False for broken symbolic links.
        """
        return self.type is not None

    @property
    def valid(self):
        """
        True if this file/folder exists, False if it doesn't. This will be
        False for broken symbolic links; use self.exists if you want an
        alternative that returns True for broken symbolic links.
        """
        return self.dereference(True).exists
    
    @property
    def is_broken(self):
        """
        True if this File is a symbolic link that is broken, False if it isn't.
        A symbolic link that points to a broken symbolic link is itself
        considered to be broken.
        """
        return self.is_link and not self.dereference(True).exists
    
    @property
    def is_file(self):
        """
        True if this File is a file, False if it isn't. If the file/folder
        doesn't actually exist yet, this will be False.
        
        If this file is a symbolic link that points to a file, this will be
        True.
        """
        return self.dereference(True).type is FILE
    
    @property
    def is_folder(self):
        """
        True if this File is a folder, False if it isn't. If the file/folder
        doesn't actually exist yet, this will be False.
        
        If this file is a symbolic link that points to a folder, this will be
        True.
        """
        return self.dereference(True).type is FOLDER
    
    @property
    def is_directory(self):
        """
        Same as self.is_folder.
        """
        return self.is_folder
    
    @property
    def is_link(self):
        """
        True if this File is a symbolic link, False if it isn't. This will be
        True even for broken symbolic links.
        """
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
        
        This also does not currently preserve file attributes or permissions;
        such abilities will be added soon.
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
        
        The newly-created file in the specified folder will be returned as per
        other.child(self.name).
        """
        new_file = other.child(self.name)
        self.copy_to(new_file, overwrite)
        return new_file

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
        """
        A list of all of the children of this file, as a list of File objects.
        If this file is not a folder, the value of this property is None.
        """
    
    @abstractproperty
    def child_names(self):
        """
        A list of the names of all of the children of this file, as a list of
        strings. If this file is not a folder, the value of this property is
        None.
        """

    def recurse(self, filter=None, include_self=True, recurse_skipped=True):
        """
        A generator that recursively yields all child File objects of this file.
        Files and directories (and the files and directories contained within
        them, and so on) are all included.
        
        A filter function accepting one argument can be specified. It will be
        called for each file and folder. It can return one of True, False,
        SKIP, YIELD, or RECURSE, with the behavior of each outlined in the
        following table::
            
                                  Don't yield   Do yield
                                +-------------+----------+
            Don't recurse into  | SKIP        | YIELD    |
                                +-------------+----------+
            Do recurse into     | RECURSE     | True     |
                                +-------------+----------+
            
            False behaves the same as RECURSE if recurse_skipped is True, or
            SKIP otherwise.
        
        If include_self is True (the default), this file (a.k.a. self) will be
        yielded as well (if it matches the specified filter function). If it's
        False, only this file's children (and their children, and so on) will
        be yielded.
        """
        include = True if filter is None else filter(self)
        if include in (YIELD, True) and include_self:
            yield self
        if include in (RECURSE, True) or (recurse_skipped and not include):
            for child in self.children or []:
                for f in child.recurse(filter, True, recurse_skipped):
                    yield f


class WorkingDirectory(object):
    __metaclass__ = ABCMeta
    
    @abstractmethod
    def change_to(self):
        """
        Sets the current working directory to self.
        
        Since File instances internally store paths in absolute form, other
        File instances will continue to work just fine after this is called.
        
        If you need to restore the working directory at any point, you might
        want to consider using :obj:`self.as_working <as_working>` instead.
        """
    
    def cd(self):
        """
        An alias for :obj:`self.change_to() <change_to>`.
        """
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
    
    @abstractmethod
    def delete(self, ignore_missing=False):
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
    
    @abstractmethod
    def link_to(self, target):
        """
        Creates this file as a symbolic link pointing to other, which can be
        a pathname or an object of the same type as self. Note that if it's a
        pathname, a symbolic link will be created with the exact path
        specified; it will therefore be absolute if the path is absolute or
        relative (to the link itself) if the path is relative. If an object of
        the same type as self, however, is used, the symbolic link will always
        be absolute.
        """
    
    @abstractmethod
    def open_for_writing(self, append=False):
        """
        Open this file for reading in binary mode and return a Python file-like
        object from which this file's contents can be read.
        
        If append is False, the file's contents will be erased and the returned
        stream positioned at the beginning of the (now empty) file. If append
        is True, the file's contents will not be erased, and the returned
        stream will be positioned at the end of the file.
        
        Note that some implementations (currently only SMBFile) don't have
        native support for writing files remotely; support in such
        implementations can be emulated by returning a wrapper around a
        temporary file that, when closed, uploads itself to the location of
        the file to be written. As a result, objects returned from
        open_for_writing should be closed before calling open_for_reading on
        the same file.
        """

    def append(self, data):
        """
        Append the specified data to the end of this file.
        """
        with self.open_for_writing(append=True) as f:
            f.write(data)

    def mkdir(self, silent=False):
        """
        An alias for self.create_folder(ignore_existing=silent).
        """
        self.create_folder(ignore_existing=silent)
    
    def mkdirs(self, silent=False):
        """
        An alias for self.create_folder(ignore_existing=silent, recursive=True).
        """
        self.create_folder(ignore_existing=silent, recursive=True)
    
    makedirs = mkdirs

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


class ReadWrite(Readable, Writable):
    __metaclass__ = ABCMeta
    
    def rename_to(self, other):
        """
        Rename this file or folder to the specified name, which should be
        another file object (but need not be of the same type as self).
        
        The default implementation simply does::
        
            self.copy_to(other)
            self.delete()
        
        (which, as a note, doesn't work for directories yet, so at present
        directories can't be renamed across different subclasses). Subclasses
        are free to provide a more specialized implementation for renames to
        files of the same type; File and SSHFile, for example, make use of
        native functions to speed up such renames (and to allow them to work
        with directories at present).
        """
        self.copy_to(other)
        self.delete()

















