from fileutils.interface import BaseFile, FileSystem
from fileutils.constants import FILE, LINK
from fileutils.local import File as _File
from fileutils.ssh import SSHFile as _SSHFile
try:
    import urllib2, urlparse
except ImportError:
    from urllib import request as urllib2, parse as urlparse
import os.path

try:
    import requests
except ImportError:
    requests = None

if requests:
    REDIRECT_CODES = (requests.codes.moved_permanently,
                      requests.codes.found,
                      requests.codes.temporary_redirect,
                      requests.codes.see_other)
    SUCCESS_CODES = (requests.codes.ok,)


def sane_urlparse(url):
    """
    An alternative to urlparse used by this module that works around
    http://bugs.python.org/issue7904
    """
    scheme, netloc, path, params, query, fragment = urlparse.urlparse(url)
    if path.startswith("//") and not netloc:
        netloc, _, path = path[2:].partition("/")
    return urlparse.ParseResult(scheme, netloc, path, params, query, fragment)


class URLFileSystem(FileSystem):
    # Only used for URLs of schemes (like HTTP) that don't have another
    # associated FileSystem subclass (like SSHFileSystem and LocalFileSystem)
    def __init__(self, scheme, netloc):
        self._scheme = scheme
        self._netloc = netloc
    
    def child(self, path):
        return URL(urlparse.ParseResult(self._scheme, self._netloc, path, '', '', '').geturl())
    
    @property
    def roots(self):
        return [self.child('')]
    
    def __cmp__(self, other):
        if not isinstance(other, URLFileSystem):
            return NotImplemented
        return cmp(self._scheme, other._scheme) or cmp(self._netloc, other._netloc)
    
    def __hash__(self):
        return hash((self._scheme, self._netloc))
    
    def __repr__(self):
        return "fileutils.URLFileSystem({0!r}, {1!r})".format(self._scheme, self._netloc)
    
    __str__ = __repr__


class URL(BaseFile):
    """
    A concrete file implementation exposing a file-like interface to URLs.
    
    This class supports several different URL schemes:
    
     * ssh: URLs of the form ssh://[user[:pass]@]host[:port]/[path] are
       converted to instances of SSHFile using SSHFile.connect().
     * file: URLs of the form file:/// are converted to instances of File,
       so they can be read, written, and listed as per usual.
     * All other schemes supported by urllib2 are supported by URL.
    """
    # NOTE: We currently discard path parameters, the query string, and the
    # fragment in the result of self.parent and self.child().
    
    type = FILE
    link_target = None
    _sep = "/"
    
    def __new__(cls, url):
        # Pass through if it's already a file. This allows converting
        # things that might be a URL string or a file object to a file
        # object with URL(string_or_file), similar to what File allows with
        # other File objects.
        if isinstance(url, BaseFile):
            return url
        scheme, netloc, path, _, _, _ = sane_urlparse(url)
        # If it's a file:// URL, return a fileutils.local.File wrapping
        # the underlying path. The requests module doesn't like file:///
        # URLs, and this fixes the problem quite nicely while also
        # offering additional conveniences (like the ability to "write"
        # to file:/// URLs).
        # Also pretend it's a file if it doesn't have a scheme or the
        # scheme's exactly one letter long (Windows paths look like this).
        if scheme == "file" and url[4:7] == "://":
            # Don't even bother trying to reconstruct the real path from the
            # parsed url; just send in everything after file://, but prefix it
            # with a slash just in case it's missing one.
            return _File('/' + url[7:])
        if len(scheme) == 1 or not scheme:
            # Also a path. On Windows, the drive letter in a path containing
            # one will be interpreted as the scheme, hence our check for
            # single-letter schemes.
            return _File(url)
        # If it's an ssh:// URL, return a fileutils.ssh.SSHFile connected
        # to the URL in question. SSHFiles learned the ability to close
        # themselves when nothing else references them a few minutes ago,
        # so there's no need for the user to know that the returned object
        # is an SSHFile.
        if scheme in ("ssh", "sftp"):
            user_part, _, host_part = netloc.rpartition("@")
            username, _, password = user_part.partition(":")
            host, _, port = host_part.partition(":")
            return _SSHFile.connect(host=host,
                                    username=username or None,
                                    password=password or None,
                                    port=int(port or 22)).child(path or "/")
        else:
            return object.__new__(cls)
    
    def __init__(self, url):
        self._url = sane_urlparse(url)
        # Normalize out trailing slashes in the path when comparing URLs.
        # TODO: We treat http://foo/a and http://foo/a/ as identical both
        # here and in self.parent, self.child, and so forth; decide if this
        # is really the right thing to do.
        self._normal_url = self._url._replace(path=self._url.path.rstrip("/"))
    
    @staticmethod
    def child_of(parent, url_or_path):
        """
        If url_or_path, a string, looks like a relative path, return
        parent.child(url_or_path). Otherwise, return URL(url_or_path).
        """
        scheme, netloc, path, _, _, _ = sane_urlparse(url_or_path)
        if path[0:1] not in ('/', '\\') and not scheme:
            # Looks like a relative path; pass through to parent.
            return parent.child(url_or_path)
        else:
            # Doesn't look like a relative path.
            return URL(url_or_path)
    
    @property
    def filesystem(self):
        return URLFileSystem(self._url.scheme, self._url.netloc)
    
    @property
    def type(self):
        response = requests.head(self._url.geturl(), allow_redirects=False)
        if response.status_code in SUCCESS_CODES:
            return FILE
        elif response.status_code in REDIRECT_CODES:
            return LINK
        else:
            return None
    
    @property
    def link_target(self):
        response = requests.head(self._url.geturl(), allow_redirects=False)
        if response.status_code in REDIRECT_CODES:
            return response.headers["Location"]
        else:
            return None
    
    @property
    def size(self):
        # TODO: We can save an extra request by just making the request
        # against our original URL and handling 30* redirects manually
        # (perhaps recursively call URL(response.headers["location"]).size)
        response = requests.head(self.dereference(recursive=True)._url.geturl())
        if response.status_code in SUCCESS_CODES:
            try:
                return int(response.headers["content-length"])
            except KeyError: # Fallback. Might be a good idea to add a
                # parameter to disable this and just raise an exception.
                size = 0
                for block in self.read_blocks():
                    size += len(block)
                return size
        else:
            return 0

    def dereference(self, recursive=False):
        link_target = self.link_target
        if link_target is None: # We're not a redirect
            return self
        target = (self.parent or self).child(link_target)
        if recursive:
            return target.dereference(recursive=True)
        else:
            return target
        
    def open_for_reading(self):
        # TODO: See how the returned object handles stream termination
        # before the number of bytes specified by the content-length header
        # have been read, and wrap it with a stream that performs such
        # checks if it doesn't already
        stream = urllib2.urlopen(self._url.geturl())
        # urllib.addinfourl objects don't provide __enter__ and __exit__;
        # patch the returned object to have them
        if not hasattr(stream, "__enter__"):
            def __enter__():
                return stream
            def __exit__(*args):
                stream.close()
            stream.__enter__ = __enter__
            stream.__exit__ = __exit__
        return stream
    
    def child(self, *names):
        if not names:
            return self
        path = self._url.path
        if not path.endswith("/"):
            path = path + "/"
        new_url = urlparse.urljoin(self._url._replace(path=path).geturl(), names[0])
        return URL(new_url).child(*names[1:])
    
    @property
    def parent(self, *names):
        path = self._url.path.rstrip("/")
        if not path: # Nothing left, so we must be at the root
            return None
        base, _, _ = path.rpartition("/")
        return URL()
        return URL(self._url._replace(path=base, params='', query='', fragment='').geturl())
    
    def get_path_components(self, relative_to=None):
        if relative_to:
            raise Exception("URLs don't yet support "
                            "get_path_components(relative_to=...)")
        # The list comprehension filters out empty names which are
        # meaningless to nearly every web server I've used. If there ends
        # up being a practical need for preserving these somehow, I'll
        # probably expose them as another property. 
        return [""] + [c for c in self._url.path.split("/") if c]
    
    @property
    def url(self):
        return self._url.geturl()
        
    def __str__(self):
        return "fileutils.URL(%r)" % self._url.geturl()
    
    __repr__ = __str__
    
    # Use __cmp__ instead of the rich comparison operators for brevity
    def __cmp__(self, other):
        if not isinstance(other, URL):
            return NotImplemented
        return cmp(self._url, other._url)
    
    def __hash__(self):
        return hash(self._url)
    
    def __nonzero__(self):
        return True
    
    def same_as(self, other):
        return (BaseFile.same_as(self, other) and
                self._url._replace(path="") == other._url._replace(path=""))
