"""
Backport of Python 3.3's reworked OS/IO exception hierarchy (see PEP 3151).
"""

import os
import errno

class BlockingIOError(OSError): pass
class ChildProcessError(OSError): pass
class ConnectionError(OSError): pass
class FileExistsError(OSError): pass
class FileNotFoundError(OSError): pass
class InterruptedError(OSError): pass
class IsADirectoryError(OSError): pass
class NotADirectoryError(OSError): pass
class PermissionError(OSError): pass
class ProcessLookupError(OSError): pass
class TimeoutError(OSError): pass

class BrokenPipeError(ConnectionError): pass
class ConnectionAbortedError(ConnectionError): pass
class ConnectionRefusedError(ConnectionError): pass
class ConnectionResetError(ConnectionError): pass

class_table = {
    # Subclasses of OSError
    errno.EAGAIN: BlockingIOError,
    errno.EALREADY: BlockingIOError,
    errno.EWOULDBLOCK: BlockingIOError,
    errno.EINPROGRESS: BlockingIOError,
    errno.ECHILD: ChildProcessError,
    errno.EEXIST: FileExistsError,
    errno.ENOENT: FileNotFoundError,
    errno.EINTR: InterruptedError,
    errno.EISDIR: IsADirectoryError,
    errno.ENOTDIR: NotADirectoryError,
    errno.EACCES: PermissionError,
    errno.EPERM: PermissionError,
    errno.ESRCH: ProcessLookupError,
    errno.ETIMEDOUT: TimeoutError,
    # ConnectionError subclasses
    errno.EPIPE: BrokenPipeError,
    errno.ESHUTDOWN: BrokenPipeError,
    errno.ECONNABORTED: ConnectionAbortedError,
    errno.ECONNREFUSED: ConnectionRefusedError,
    errno.ECONNRESET: ConnectionResetError
}

default_code_table = {
    BlockingIOError: errno.EWOULDBLOCK,
    ChildProcessError: errno.ECHILD,
    FileExistsError: errno.EEXIST,
    FileNotFoundError: errno.ENOENT,
    InterruptedError: errno.EINTR,
    IsADirectoryError: errno.EISDIR,
    NotADirectoryError: errno.ENOTDIR,
    PermissionError: errno.EPERM,
    ProcessLookupError: errno.ESRCH,
    TimeoutError: errno.ETIMEDOUT,
    
    BrokenPipeError: errno.EPIPE,
    ConnectionAbortedError: errno.ECONNABORTED,
    ConnectionRefusedError: errno.ECONNREFUSED,
    ConnectionResetError: errno.ECONNRESET
}

TYPES_TO_CONVERT = (OSError, IOError)
# On Windows, also convert WindowsError instances
try:
    TYPES_TO_CONVERT += (WindowsError,) #@UndefinedVariable
except NameError:
    pass


def convert(exception, filename=None):
    # We use a member check instead of a call to isinstance() to avoid
    # re-converting exceptions that are already an instance of one of our
    # subclasses of OSError
    if type(exception) in TYPES_TO_CONVERT:
        if exception.errno in class_table:
            new_class = class_table[exception.errno]
            new_filename = filename or exception.filename
            # Don't pass in the filename if we don't have one to pass in.
            # Passing None as the filename to OSError.__init__ causes the
            # resulting exception's __str__ to end with ": None", which doesn't
            # happen when we just omit the parameter altogether.
            if new_filename is None:
                return new_class(exception.errno, exception.strerror)
            else:
                return new_class(exception.errno, exception.strerror,
                                 filename or exception.filename)
    # Wasn't a type to convert or wasn't an errno we know about. Return the
    # exception as-is.
    return exception


class Convert(object):
    def __init__(self, filename=None):
        self.filename = filename
    
    def __enter__(self):
        pass
    
    def __exit__(self, exception_type, value, traceback):
        new_exception = convert(value, self.filename)
        # If convert() returned a new exception, raise it
        if new_exception is not value:
            raise new_exception
        # Otherwise, do nothing, and let the old exception propagate out.


def generate(exception_class, filename=None):
    try:
        error_code = default_code_table[exception_class]
    except KeyError:
        # Fall back to constructing the exception without an error code
        if filename is None:
            return exception_class()
        else:
            return exception_class(filename)
    # Got the error code. Figure out its message.
    message = os.strerror(error_code)
    # Then return a new instance of exception_class.
    if filename is None:
        return exception_class(error_code, message)
    else:
        return exception_class(error_code, message, filename)






















