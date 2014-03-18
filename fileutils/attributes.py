
import stat

class AttributeSet(object):
    """
    A set of attributes on a file.
    
    Each of the subclasses of this class provide an interface to a particular
    set of filesystem attributes. PosixPermissions, for example, provides an
    interface to POSIX-style permissions and mode bits, and ExtendedAttributes
    provides a platform-neutral interface to user-defined extended attributes.
    
    AttributeSet instances can be obtained from any BaseFile instance's
    attributes property. This property is a dictionary whose keys are the
    various subclasses of AttributeSet (the class objects themselves, not
    instances of said classes) and whose values are instances of the
    corresponding subclass. For example, one could, on a POSIX system, get an
    instance of PosixPermissions corresponding to /home with::
    
        File('/home').attributes[PosixPermissions]
    
    Instances of these subclasses can then be used to read and modify the
    file's attributes in a subclass specific manner. PosixPermissions has
    properties that can be used to set the various mode bits, so, for example,
    one could grant a particular file's group permission to write to that file
    thus::
    
        some_file.attributes[PosixPermissions].group.write = True
    """
    def copy_to(self, other):
        """
        Copy attributes exposed by this attribute set to the specified
        attribute set.
        
        All of the subclasses of AttributeSet provide implementations of this
        method. Subclasses of those subclasses shouldn't need to override this.
        """
        raise NotImplementedError
    
    @property
    def copy_by_default(self):
        """
        True if this attribute set should be copied by default, false if it
        shouldn't be.
        
        Functions like BaseFile.copy_attributes_to (and, by extension,
        BaseFile.copy_to and BaseFile.copy_into) consult this property when
        they're not given further direction as to which attribute sets should
        be copied from one file to another.
        
        All of the subclasses of AttributeSet provide implementations of this
        property. Subclasses of those classes shouldn't need to override this.
        """
        raise NotImplementedError


class PosixPermissions(AttributeSet):
    """
    An attribute set providing access to a file's POSIX permission and mode
    bits.
    """
    copy_by_default = True
    
    @property
    def mode(self):
        """
        The numerical mode of this file.
        
        Setting the value of this property causes a call to chmod to be made,
        unless this file is a symbolic link and the underlying platform doesn't
        support custom permissions on symbolic links (Linux is such a
        platform); in such a case, nothing whatsoever happens, and the new mode
        is silently ignored.
        """
        raise NotImplementedError
    
    def set(self, mask, value):
        # Takes one of the stat.S_* constants
        mode = self.mode
        mode &= ~mask
        if value:
            mode |= mask
        self.mode = mode
    
    def get(self, mask):
        return bool(self.mode & mask)
    
    @property
    def user(self):
        """
        An object with three properties: read, write, and execute. These
        properties are all booleans corresponding to the respective user
        permission bit. They can be set to new values to modify the permissions
        of the file in question.
        
        For example, one can see if this file's owner has permission to execute
        this file with::
        
            self.user.execute
        
        and one can mark the file as being executable by its owner with::
        
            self.user.execute = True
        """
        return _ModeAccessor(self, stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR)
    
    @property
    def group(self):
        return _ModeAccessor(self, stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP)
    
    @property
    def other(self):
        return _ModeAccessor(self, stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH)
    
    @property
    def setuid(self):
        """
        True if this file's setuid bit is set, false if it isn't.
        
        This property can be modified to set or clear the file's setuid flag.
        """
        return self.get(stat.S_ISUID)
    
    @setuid.setter
    def setuid(self, value):
        self.set(stat.S_ISUID, value)
    
    @property
    def setgid(self):
        """
        True if this file's setgid bit is set, false if it isn't.
        
        This property can be modified to set or clear the file's setgid flag.
        """
        return self.get(stat.S_ISGID)
    
    @setgid.setter
    def setgid(self, value):
        self.set(stat.S_ISGID, value)
    
    @property
    def sticky(self):
        return self.get(stat.S_ISVTX)
    
    @sticky.setter
    def sticky(self, value):
        self.set(stat.S_ISVTX, value)
    
    @property
    def execute(self):
        """
        True if any of the file's execute bits are set, false if none of them
        are.
        
        Setting the value of this property to True turns on the corresponding
        execute bit for each read bit that's set (but does not clear other
        execute bits that are already set). Setting the value of this property
        to False clears all executable bits that are set.
        """
        return bool(self.mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    
    @execute.setter
    def execute(self, value):
        mode = self.mode
        if value:
            # Set executable bits where the corresponding read bit is set
            if mode & stat.S_IRUSR:
                mode |= stat.S_IXUSR
            if mode & stat.S_IRGRP:
                mode |= stat.S_IXGRP
            if mode & stat.S_IROTH:
                mode |= stat.S_IXOTH
        else:
            # Clear all executable bits
            mode &= ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.mode = mode
    
    def copy_to(self, other):
        other.mode = self.mode


class ExtendedAttributes(AttributeSet):
    """
    An attribute set providing access to a file's extended user attributes.
    """
    copy_by_default = False
    
    def get(self, name):
        """
        Get the value of the extended attribute with the specified name, or
        raise KeyError if no such extended attribute exists.
        """
        raise NotImplementedError
    
    def set(self, name, value):
        """
        Set the value of the specified extended attribute to the specified
        value.
        """
        raise NotImplementedError
    
    def list(self):
        """
        Return a list of strings naming all of the extended attributes present
        on this file.
        """
        raise NotImplementedError
    
    def delete(self, name):
        """
        Delete the extended user attribute with the specified name.
        """
        raise NotImplementedError
    
    def copy_to(self, other):
        # Copy over our attributes. Note that we specifically don't delete the
        # other file's existing attributes first to avoid trampling on other
        # attribute sets that are just fronts for certain extended attributes
        # (like the future FileMimeType will be, at least on Linux).
        for name in self.list():
            try:
                other.set(name, self.get(name))
            except EnvironmentError:
                # Probably because the target file is on a filesystem that
                # places restrictions on the names of extended attributes; just
                # ignore for now. Might want to consider raising some sort of
                # warning later.
                pass


class _ModeAccessor(object):
    def __init__(self, attributes, r, w, x):
        self._attributes = attributes
        self._r = r
        self._w = w
        self._x = x
    
    @property
    def read(self):
        return self._attributes.get(self._r)
    
    @read.setter
    def read(self, value):
        self._attributes.set(self._r, value)
    
    @property
    def write(self):
        return self._attributes.get(self._w)
    
    @write.setter
    def write(self, value):
        self._attributes.set(self._w, value)
    
    @property
    def execute(self):
        return self._attributes.get(self._x)
    
    @execute.setter
    def execute(self, value):
        self._attributes.set(self._x, value)
    
    def __repr__(self):
        mode = self._attributes.mode
        r = "r" if mode & self._r else "-"
        w = "w" if mode & self._w else "-"
        x = "x" if mode & self._x else "-"
        return "<mode " + r + w + x + ">"
    
    __str__ = __repr__
