
import os.path
from nose.tools import with_setup
import fileutils
import tempfile
import shutil
import random

# Python 2.6's unittest.TestCase.assertRaises can't be used as a context
# manager, so define our own instead.
class AssertRaises(object):
    def __init__(self, *exception_types):
        self._exception_types = exception_types
    
    def __enter__(self):
        pass
    
    def __exit__(self, t, v, tb):
        # Make sure an exception was raised
        if t is None:
            raise Exception("Expected one of {0} to be raised"
                            .format(self._exception_types))
        # Suppress it only if it was of the right type
        return issubclass(t, self._exception_types)


class Base(object):
    def setup(self):
        self.temporary = tempfile.mkdtemp()
        self.cwd_before_testing = os.getcwd()
    
    def teardown(self):
        shutil.rmtree(self.temporary)
        os.chdir(self.cwd_before_testing)


class TestLocal(Base):
    def test_file_system_singleton(self):
        assert fileutils.LocalFileSystem() is fileutils.LocalFileSystem()
    
    def test_file_system_child(self):
        fs = fileutils.LocalFileSystem()
        f = fileutils.File()
        assert fs.child(f.path) == f
        assert fs.child(f.child('a').path) == f.child('a')
        assert fs.child(f.path, 'a') == f.child('a')
        assert fs.child(f.path, 'a').sibling('b') == f.child('b')
        assert fs.child(f.path, 'a').sibling('b', 'c') == f.child('b', 'c')
        assert f.child('a').child('b') == f.child('a', 'b')
        assert f.child('a', 'b') == f.child(os.path.join('a', 'b'))

    def test_local_cache_transparent(self):
        fs = fileutils.LocalFileSystem()
        name = 'file_to_cache'
        contents = 'test file contents'
        f = fileutils.File(self.temporary, name)
        f.write(contents)
        cache = fs.cache(f)
        assert cache.cache is None
        assert cache.location == f
    
    def test_file_construction(self):
        assert fileutils.File().path == os.getcwd()
        assert fileutils.File('a').path == os.path.join(os.getcwd(), 'a')
        assert fileutils.File('a', 'b').path == os.path.join(os.getcwd(), 'a', 'b')
        f = fileutils.File('a', 'b')
        assert fileutils.File(f) == f
    
    def test_roots(self):
        fs = fileutils.LocalFileSystem()
        for root in fs.roots:
            assert root.parent is None
            assert fileutils.File().child(root.path) == root
        root = fs.root
        if root is not None:
            assert root in fs.roots
    
    def test_parent(self):
        f = fileutils.File()
        assert f.parent is not None
        assert f.child('a').parent == f
        assert f.child('a', 'b').parent.parent == f
    
    def test_children(self):
        t = fileutils.File(self.temporary)
        t.child('a').mkdir()
        t.child('b').write('')
        assert t.child_names == ['a', 'b']
        assert t.children == [t.child('a'), t.child('b')]
        # Empty dir
        assert t.child('a').child_names == []
        assert t.child('a').children == []
        # File
        assert t.child('b').child_names is None
        assert t.child('b').children is None
        # Nonexistent dir
        assert t.child('c').child_names is None
        assert t.child('c').children is None
        t.child('c').mkdir()
        assert t.child_names == ['a', 'b', 'c']
        t.child('c').delete()
        assert t.child_names == ['a', 'b']
        t.child('a').child('foo').mkdir()
        t.child('a').child('bar').mkdir()
        t.child('d').link_to('a')
        # Symlink
        assert t.child('d').child_names == ['bar', 'foo']
        # Children should be in symlink, not in link target
        assert t.child('d').children == [t.child('d').child('bar'),
                                         t.child('d').child('foo')]
    
    def test_size(self):
        t = fileutils.File(self.temporary)
        for _ in range(10):
            data = ' ' * random.randrange(1, 10000)
            t.child('a').write(data)
            assert t.child('a').size == len(data)
            assert t.child('b').size == 0 # TODO: Would None make more sense?
            t.child('b').link_to('a')
            assert t.child('b').size == len(data)
            t.child('b').delete()
        t.child('c').link_to('d')
        assert t.child('c').size == 0 # TODO: Ditto
        t.child('e').mkdir()
        t.child('e', 'a').write('something')
        t.child('e', 'b').write('else')
        assert t.child('e').size == 13
    
    def test_symlink(self):
        t = fileutils.File(self.temporary)
        t.child('a').mkdir()
        assert t.child('a').link_target is None
        assert t.child('b').link_target is None
        t.child('b').link_to(t.child('a'))
        assert t.child('b').link_target == t.child('a').path
        assert t.child('b').dereference() == t.child('a')
        t.child('b').delete()
        t.child('b').link_to('a')
        assert t.child('b').link_target == 'a'
        assert t.child('b').dereference() == t.child('a')
        t.child('c').link_to(t.child('b'))
        assert t.child('c').dereference() == t.child('b')
        assert t.child('c').dereference(recursive=True) == t.child('a')
    
    def test_cd(self):
        t = fileutils.File(self.temporary)
        with AssertRaises(fileutils.exceptions.FileNotFoundError):
            t.child('a').cd()
        t.child('a').mkdir()
        old_cwd = fileutils.File()
        assert old_cwd.path == os.getcwd()
        t.child('a').cd()
        assert t.child('a').path == os.getcwd()
        assert t.child('a') == fileutils.File()
        old_cwd.cd()
        assert old_cwd.path == os.getcwd()
    
    def test_as_working(self):
        t = fileutils.File(self.temporary)
        with AssertRaises(fileutils.exceptions.FileNotFoundError):
            with t.child('a').as_working:
                pass
        t.child('a').mkdir()
        old_cwd = fileutils.File()
        with t.child('a').as_working as a:
            assert t.child('a') == a
            assert t.child('a') == fileutils.File()
        assert old_cwd == fileutils.File()
    
    def test_path_components(self):
        t = fileutils.File(self.temporary)
        t_components = t.path_components
        assert len(t_components) >= 1
        assert t_components[-1] == t.name
        a_components = t.child('a').path_components
        assert a_components[:len(t_components)] == t_components
        assert a_components[len(t_components):] == ['a']
        b_components = t.child('a', 'b').path_components
        assert b_components[:len(t_components)] == t_components
        assert b_components[len(t_components):] == ['a', 'b']
        assert t.child('a', 'b').get_path_components(relative_to=t) == ['a', 'b']
    
    def test_bool(self):
        t = fileutils.File(self.temporary)
        assert bool(t)
        assert bool(t.child('bogus'))











