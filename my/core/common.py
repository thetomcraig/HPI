from glob import glob as do_glob
from pathlib import Path
from datetime import datetime
import functools
import types
from typing import Union, Callable, Dict, Iterable, TypeVar, Sequence, List, Optional, Any, cast, Tuple, TYPE_CHECKING
import warnings

# some helper functions
PathIsh = Union[Path, str]

# TODO only used in tests? not sure if useful at all.
# TODO port annotations to kython?..
def import_file(p: PathIsh, name: Optional[str]=None) -> types.ModuleType:
    p = Path(p)
    if name is None:
        name = p.stem
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, p)
    foo = importlib.util.module_from_spec(spec)
    loader = spec.loader; assert loader is not None
    loader.exec_module(foo) # type: ignore[attr-defined]
    return foo


def import_from(path: PathIsh, name: str) -> types.ModuleType:
    path = str(path)
    import sys
    try:
        sys.path.append(path)
        import importlib
        return importlib.import_module(name)
    finally:
        sys.path.remove(path)


def import_dir(path: PathIsh, extra: str='') -> types.ModuleType:
    p = Path(path)
    if p.parts[0] == '~':
        p = p.expanduser() # TODO eh. not sure about this..
    return import_from(p.parent, p.name + extra)


T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')

def the(l: Iterable[T]) -> T:
    it = iter(l)
    try:
        first = next(it)
    except StopIteration as ee:
        raise RuntimeError('Empty iterator?')
    assert all(e == first for e in it)
    return first


# TODO more_itertools.bucket?
def group_by_key(l: Iterable[T], key: Callable[[T], K]) -> Dict[K, List[T]]:
    res: Dict[K, List[T]] = {}
    for i in l:
        kk = key(i)
        lst = res.get(kk, [])
        lst.append(i)
        res[kk] = lst
    return res


def _identity(v: T) -> V:
    return cast(V, v)

def make_dict(l: Iterable[T], key: Callable[[T], K], value: Callable[[T], V]=_identity) -> Dict[K, V]:
    res: Dict[K, V] = {}
    for i in l:
        k = key(i)
        v = value(i)
        pv = res.get(k, None) # type: ignore
        if pv is not None:
            raise RuntimeError(f"Duplicate key: {k}. Previous value: {pv}, new value: {v}")
        res[k] = v
    return res


Cl = TypeVar('Cl')
R = TypeVar('R')

def cproperty(f: Callable[[Cl], R]) -> R:
    return property(functools.lru_cache(maxsize=1)(f)) # type: ignore


# https://stackoverflow.com/a/12377059/706389
def listify(fn=None, wrapper=list):
    """
    Wraps a function's return value in wrapper (e.g. list)
    Useful when an algorithm can be expressed more cleanly as a generator
    """
    def listify_return(fn):
        @functools.wraps(fn)
        def listify_helper(*args, **kw):
            return wrapper(fn(*args, **kw))
        return listify_helper
    if fn is None:
        return listify_return
    return listify_return(fn)


# todo use in bluemaestro
# def dictify(fn=None, key=None, value=None):
#     def md(it):
#         return make_dict(it, key=key, value=value)
#     return listify(fn=fn, wrapper=md)


from ..kython.klogging import setup_logger, LazyLogger


Paths = Union[Sequence[PathIsh], PathIsh]

# TODO support '' for emtpy path
DEFAULT_GLOB = '*'
def get_files(pp: Paths, glob: str=DEFAULT_GLOB, sort: bool=True) -> Tuple[Path, ...]:
    """
    Helper function to avoid boilerplate.

    Tuple as return type is a bit friendlier for hashing/caching, so hopefully makes sense
    """
    # TODO FIXME mm, some wrapper to assert iterator isn't empty?
    sources: List[Path]
    if isinstance(pp, Path):
        sources = [pp]
    elif isinstance(pp, str):
        if pp == '':
            # special case -- makes sense for optional data sources, etc
            return () # early return to prevent warnings etc
        sources = [Path(pp)]
    else:
        sources = [Path(p) for p in pp]

    def caller() -> str:
        import traceback
        # TODO ugh. very flaky... -3 because [<this function>, get_files(), <actual caller>]
        return traceback.extract_stack()[-3].filename

    paths: List[Path] = []
    for src in sources:
        if src.parts[0] == '~':
            src = src.expanduser()
        if src.is_dir():
            gp: Iterable[Path] = src.glob(glob)
            paths.extend(gp)
        else:
            ss = str(src)
            if '*' in ss:
                if glob != DEFAULT_GLOB:
                    warnings.warn(f"{caller()}: treating {ss} as glob path. Explicit glob={glob} argument is ignored!")
                paths.extend(map(Path, do_glob(ss)))
            else:
                if not src.is_file():
                    raise RuntimeError(f"Expected '{src}' to exist")
                # todo assert matches glob??
                paths.append(src)

    if sort:
        paths = list(sorted(paths))

    if len(paths) == 0:
        # todo make it conditionally defensive based on some global settings
        # TODO not sure about using warnings module for this
        import traceback
        warnings.warn(f'{caller()}: no paths were matched against {paths}. This might result in missing data.')
        traceback.print_stack()

    return tuple(paths)


# TODO annotate it, perhaps use 'dependent' type (for @doublewrap stuff)
if TYPE_CHECKING:
    from typing import Callable, TypeVar
    from typing_extensions import Protocol
    # TODO reuse types from cachew? although not sure if we want hard dependency on it in typecheck time..
    # I guess, later just define pass through once this is fixed: https://github.com/python/typing/issues/270
    # ok, that's actually a super nice 'pattern'
    F = TypeVar('F')
    class McachewType(Protocol):
        def __call__(self, cache_path: Any=None, *, hashf: Any=None, chunk_by: int=0, logger: Any=None) -> Callable[[F], F]:
            ...

    mcachew: McachewType

def mcachew(*args, **kwargs): # type: ignore[no-redef]
    """
    Stands for 'Maybe cachew'.
    Defensive wrapper around @cachew to make it an optional dependency.
    """
    try:
        import cachew
    except ModuleNotFoundError:
        warnings.warn('cachew library not found. You might want to install it to speed things up. See https://github.com/karlicoss/cachew')
        return lambda orig_func: orig_func
    else:
        import cachew.experimental
        cachew.experimental.enable_exceptions()  # TODO do it only once?
        return cachew.cachew(*args, **kwargs)


@functools.lru_cache(1)
def _magic():
    import magic # type: ignore
    return magic.Magic(mime=True)


# TODO could reuse in pdf module?
import mimetypes # todo do I need init()?
# todo wtf? fastermime thinks it's mime is application/json even if the extension is xz??
# whereas magic detects correctly: application/x-zstd and application/x-xz
def fastermime(path: PathIsh) -> str:
    paths = str(path)
    # mimetypes is faster
    (mime, _) = mimetypes.guess_type(paths)
    if mime is not None:
        return mime
    # magic is slower but returns more stuff
    # TODO Result type?; it's kinda racey, but perhaps better to let the caller decide?
    return _magic().from_file(paths)


Json = Dict[str, Any]


from typing import TypeVar, Callable, Generic

_C = TypeVar('_C')
_R = TypeVar('_R')

# https://stackoverflow.com/a/5192374/706389
class classproperty(Generic[_R]):
    def __init__(self, f: Callable[[_C], _R]) -> None:
        self.f = f

    def __get__(self, obj: None, cls: _C) -> _R:
        return self.f(cls)


# hmm, this doesn't really work with mypy well..
# https://github.com/python/mypy/issues/6244
# class staticproperty(Generic[_R]):
#     def __init__(self, f: Callable[[], _R]) -> None:
#         self.f = f
#
#     def __get__(self) -> _R:
#         return self.f()

# TODO maybe use opaque mypy alias?
tzdatetime = datetime


fromisoformat: Callable[[str], datetime]
import sys
if sys.version_info.minor >= 7:
    # prevent mypy on py3.6 from complaining...
    fromisoformat_real = datetime.fromisoformat # type: ignore[attr-defined]
    fromisoformat = fromisoformat_real
else:
    from .py37 import fromisoformat


# TODO doctests?
def isoparse(s: str) -> tzdatetime:
    """
    Parses timestamps formatted like 2020-05-01T10:32:02.925961Z
    """
    # TODO could use dateutil? but it's quite slow as far as I remember..
    # TODO support non-utc.. somehow?
    assert s.endswith('Z'), s
    s = s[:-1] + '+00:00'
    return fromisoformat(s)


import re
# https://stackoverflow.com/a/295466/706389
def get_valid_filename(s: str) -> str:
    s = str(s).strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '', s)


from typing import Generic, Sized, Callable


# X = TypeVar('X')
def _warn_iterator(it, f: Any=None):
    emitted = False
    for i in it:
        yield i
        emitted = True
    if not emitted:
        warnings.warn(f"Function {f} didn't emit any data, make sure your config paths are correct")


# TODO ugh, so I want to express something like:
# X = TypeVar('X')
# C = TypeVar('C', bound=Iterable[X])
# _warn_iterable(it: C) -> C
# but apparently I can't??? ugh.
# https://github.com/python/typing/issues/548
# I guess for now overloads are fine...

from typing import overload
X = TypeVar('X')
@overload
def _warn_iterable(it: List[X]    , f: Any=None) -> List[X]    : ...
@overload
def _warn_iterable(it: Iterable[X], f: Any=None) -> Iterable[X]: ...
def _warn_iterable(it, f=None):
    if isinstance(it, Sized):
        sz = len(it)
        if sz == 0:
            warnings.warn(f"Function {f} returned empty container, make sure your config paths are correct")
        return it
    else:
        return _warn_iterator(it, f=f)


# ok, this seems to work...
# https://github.com/python/mypy/issues/1927#issue-167100413
FL = TypeVar('FL', bound=Callable[..., List])
FI = TypeVar('FI', bound=Callable[..., Iterable])

@overload
def warn_if_empty(f: FL) -> FL: ...
@overload
def warn_if_empty(f: FI) -> FI: ...


def warn_if_empty(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        res = f(*args, **kwargs)
        return _warn_iterable(res, f=f)
    return wrapped # type: ignore


# hacky hook to speed up for 'hpi doctor'
# todo think about something better
QUICK_STATS = False


C = TypeVar('C')
# todo not sure about return type...
def stat(func: Callable[[], Iterable[C]]) -> Dict[str, Any]:
    from more_itertools import ilen, take, first

    it = iter(func())
    res: Any
    if QUICK_STATS:
        initial = take(100, it)
        res = len(initial)
        if first(it, None) is not None: # todo can actually be none...
            # haven't exhausted
            res = f'{res}+'
    else:
        res = ilen(it)


    return {
        func.__name__: res,
    }
