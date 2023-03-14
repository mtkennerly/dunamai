import datetime as dt
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional

try:
    import importlib.metadata as ilm
except ImportError:
    import importlib_metadata as ilm  # type: ignore

import pytest

from dunamai import (
    bump_version,
    check_version,
    get_version,
    Version,
    serialize_pep440,
    serialize_pvp,
    serialize_semver,
    Pattern,
    Style,
    Vcs,
    _run_cmd,
    VERSION_SOURCE_PATTERN,
)


@contextmanager
def chdir(where: Path) -> Iterator[None]:
    start = Path.cwd()
    os.chdir(str(where))
    try:
        yield
    finally:
        os.chdir(str(start))


def make_run_callback(where: Path) -> Callable:
    def inner(command, expected_code: int = 0):
        _, out = _run_cmd(command, where=where, codes=[expected_code])
        return out

    return inner


def make_from_callback(function: Callable, mock_commit: Optional[str] = "abc") -> Callable:
    def inner(*args, **kwargs):
        version = function(*args, **kwargs)
        if version.commit and mock_commit:
            version.commit = mock_commit
        return version

    return inner


from_any_vcs = make_from_callback(Version.from_any_vcs)
from_any_vcs_unmocked = make_from_callback(Version.from_any_vcs, mock_commit=None)
from_explicit_vcs = make_from_callback(Version.from_vcs)


def test__pattern__regex() -> None:
    assert Pattern.Default.regex() == VERSION_SOURCE_PATTERN
    assert Pattern.DefaultUnprefixed.regex() != VERSION_SOURCE_PATTERN


def test__pattern__parse() -> None:
    assert Pattern.parse(r"(?P<base>\d+)") == r"(?P<base>\d+)"
    assert Pattern.parse("default") == Pattern.Default.regex()
    assert Pattern.parse("default-unprefixed") == Pattern.DefaultUnprefixed.regex()
    with pytest.raises(ValueError):
        Pattern.parse(r"foo")


def test__version__init() -> None:
    v = Version(
        "1", stage=("a", 2), distance=3, commit="abc", dirty=True, tagged_metadata="def", epoch=4
    )
    assert v.base == "1"
    assert v.stage == "a"
    assert v.revision == 2
    assert v.distance == 3
    assert v.commit == "abc"
    assert v.dirty
    assert v.tagged_metadata == "def"
    assert v.epoch == 4


def test__version__str() -> None:
    v = Version("1", stage=("a", 2), distance=3, commit="abc", dirty=True)
    assert str(v) == v.serialize()


def test__version__repr() -> None:
    v = Version(
        "1",
        stage=("a", 2),
        distance=3,
        commit="abc",
        dirty=True,
        tagged_metadata="tagged",
        epoch=4,
        branch="master",
        timestamp=dt.datetime(2000, 1, 2, 3, 4, 5).replace(tzinfo=dt.timezone.utc),
    )
    assert repr(v) == (
        "Version(base='1', stage='a', revision=2, distance=3, commit='abc',"
        " dirty=True, tagged_metadata='tagged', epoch=4, branch='master',"
        " timestamp=datetime.datetime(2000, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc))"
    )


def test__version__ordering() -> None:
    assert Version("0.1.0", distance=2) == Version("0.1.0", distance=2)
    assert Version("0.2.0") > Version("0.1.0")
    assert Version("0.1.0", distance=2) > Version("0.1.0", distance=1)
    with pytest.raises(TypeError):
        Version("0.1.0") == "0.1.0"
    with pytest.raises(TypeError):
        Version("0.1.0") < "0.2.0"
    assert Version("0.1.0", commit="a") != Version("0.1.0", commit="b")
    assert Version("0.1.0", dirty=True) == Version("0.1.0", dirty=True)
    assert Version("0.1.0", dirty=False) != Version("0.1.0", dirty=True)
    assert Version("0.1.0") != Version("0.1.0", dirty=True)
    assert Version("0.1.0") != Version("0.1.0", dirty=False)


def test__version__serialize__pep440() -> None:
    assert Version("0.1.0").serialize() == "0.1.0"

    assert (
        Version("1", stage=("a", 2), distance=3, commit="abc", dirty=True).serialize()
        == "1a2.post3.dev0+abc"
    )
    assert (
        Version("1", stage=("a", 2), distance=3, commit="abc", dirty=True).serialize(dirty=True)
        == "1a2.post3.dev0+abc.dirty"
    )
    assert (
        Version("1", stage=("a", 2), distance=3, commit="abc", dirty=True).serialize(metadata=False)
        == "1a2.post3.dev0"
    )
    assert (
        Version("1", stage=("a", 2), distance=3, commit="abc", dirty=True).serialize(
            metadata=False, dirty=True
        )
        == "1a2.post3.dev0"
    )

    assert (
        Version("1", stage=("a", 0), distance=3, commit="abc", dirty=False).serialize()
        == "1a0.post3.dev0+abc"
    )
    assert Version("1", stage=("a", 2), distance=0, commit="abc", dirty=False).serialize() == "1a2"
    assert (
        Version("1", stage=("a", 2), distance=3, commit="000", dirty=False).serialize()
        == "1a2.post3.dev0+000"
    )

    assert Version("1", stage=("a", None)).serialize() == "1a0"
    assert Version("1", stage=("b", 2)).serialize() == "1b2"
    assert Version("1", stage=("rc", 2)).serialize() == "1rc2"

    assert Version("0.1.0").serialize(bump=True) == "0.1.0"
    assert Version("0.1.0", distance=3).serialize(bump=True) == "0.1.1.dev3"
    assert Version("1", distance=3).serialize(bump=True) == "2.dev3"
    assert Version("0.1.0", stage=("a", None), distance=3).serialize(bump=True) == "0.1.0a2.dev3"
    assert Version("0.1.0", stage=("b", 2), distance=3).serialize(bump=True) == "0.1.0b3.dev3"

    assert Version("0.1.0", epoch=2).serialize() == "2!0.1.0"

    assert Version("0.1.0", stage=("post", 1)).serialize() == "0.1.0.post1"
    assert Version("0.1.0", stage=("post", 1), distance=3).serialize() == "0.1.0.post1.dev3"
    assert (
        Version("0.1.0", stage=("post", 1), distance=3).serialize(bump=True) == "0.1.0.post2.dev3"
    )
    assert Version("0.1.0", stage=("dev", 1)).serialize() == "0.1.0.dev1"
    assert Version("0.1.0", stage=("dev", 1), distance=3).serialize() == "0.1.0.dev4"
    assert Version("0.1.0", stage=("dev", 1), distance=3).serialize(bump=True) == "0.1.0.dev5"


def test__version__serialize__semver() -> None:
    style = Style.SemVer
    assert Version("0.1.0").serialize(style=style) == "0.1.0"

    assert (
        Version("0.1.0", stage=("alpha", 2), distance=3, commit="abc", dirty=True).serialize(
            style=style
        )
        == "0.1.0-alpha.2.post.3+abc"
    )
    assert (
        Version("0.1.0", stage=("alpha", 2), distance=3, commit="abc", dirty=True).serialize(
            dirty=True, style=style
        )
        == "0.1.0-alpha.2.post.3+abc.dirty"
    )
    assert (
        Version("0.1.0", stage=("alpha", 2), distance=3, commit="abc", dirty=True).serialize(
            metadata=False, style=style
        )
        == "0.1.0-alpha.2.post.3"
    )
    assert (
        Version("0.1.0", stage=("alpha", 2), distance=3, commit="abc", dirty=True).serialize(
            metadata=False, dirty=True, style=style
        )
        == "0.1.0-alpha.2.post.3"
    )

    assert (
        Version("0.1.0", stage=("alpha", 0), distance=3, commit="abc", dirty=False).serialize(
            style=style
        )
        == "0.1.0-alpha.0.post.3+abc"
    )
    assert (
        Version("0.1.0", stage=("alpha", 2), distance=0, commit="abc", dirty=False).serialize(
            style=style
        )
        == "0.1.0-alpha.2"
    )
    assert (
        Version("0.1.0", stage=("alpha", 2), distance=3, commit="000", dirty=False).serialize(
            style=style
        )
        == "0.1.0-alpha.2.post.3+000"
    )

    assert Version("0.1.0", stage=("alpha", None)).serialize(style=style) == "0.1.0-alpha"
    assert Version("0.1.0", stage=("beta", 2)).serialize(style=style) == "0.1.0-beta.2"
    assert Version("0.1.0", stage=("rc", 2)).serialize(style=style) == "0.1.0-rc.2"

    assert Version("0.1.0").serialize(style=style, bump=True) == "0.1.0"
    assert Version("0.1.0", distance=3).serialize(style=style, bump=True) == "0.1.1-pre.3"
    assert (
        Version("0.1.0", stage=("alpha", None), distance=3).serialize(style=style, bump=True)
        == "0.1.0-alpha.2.pre.3"
    )
    assert (
        Version("0.1.0", stage=("beta", 2), distance=4).serialize(style=style, bump=True)
        == "0.1.0-beta.3.pre.4"
    )

    assert Version("0.1.0", epoch=2).serialize(style=style) == "0.1.0"


def test__version__serialize__pvp() -> None:
    style = Style.Pvp
    assert Version("0.1.0").serialize(style=style) == "0.1.0"

    assert (
        Version("0.1.0", stage=("alpha", 2), distance=3, commit="abc", dirty=True).serialize(
            style=style
        )
        == "0.1.0-alpha-2-post-3-abc"
    )
    assert (
        Version("0.1.0", stage=("alpha", 2), distance=3, commit="abc", dirty=True).serialize(
            dirty=True, style=style
        )
        == "0.1.0-alpha-2-post-3-abc-dirty"
    )
    assert (
        Version("0.1.0", stage=("alpha", 2), distance=3, commit="abc", dirty=True).serialize(
            metadata=False, style=style
        )
        == "0.1.0-alpha-2-post-3"
    )
    assert (
        Version("0.1.0", stage=("alpha", 2), distance=3, commit="abc", dirty=True).serialize(
            metadata=False, dirty=True, style=style
        )
        == "0.1.0-alpha-2-post-3"
    )

    assert (
        Version("0.1.0", stage=("alpha", 0), distance=3, commit="abc", dirty=False).serialize(
            style=style
        )
        == "0.1.0-alpha-0-post-3-abc"
    )
    assert (
        Version("0.1.0", stage=("alpha", 2), distance=0, commit="abc", dirty=False).serialize(
            style=style
        )
        == "0.1.0-alpha-2"
    )
    assert (
        Version("0.1.0", stage=("alpha", 2), distance=3, commit="000", dirty=False).serialize(
            style=style
        )
        == "0.1.0-alpha-2-post-3-000"
    )

    assert Version("0.1.0", stage=("alpha", None)).serialize(style=style) == "0.1.0-alpha"
    assert Version("0.1.0", stage=("beta", 2)).serialize(style=style) == "0.1.0-beta-2"
    assert Version("0.1.0", stage=("rc", 2)).serialize(style=style) == "0.1.0-rc-2"

    assert Version("0.1.0").serialize(style=style, bump=True) == "0.1.0"
    assert Version("0.1.0", distance=3).serialize(style=style, bump=True) == "0.1.1-pre-3"
    assert (
        Version("0.1.0", stage=("alpha", None), distance=3).serialize(style=style, bump=True)
        == "0.1.0-alpha-2-pre-3"
    )
    assert (
        Version("0.1.0", stage=("beta", 2), distance=4).serialize(style=style, bump=True)
        == "0.1.0-beta-3-pre-4"
    )

    assert Version("0.1.0", epoch=2).serialize(style=style) == "0.1.0"


def test__version__serialize__pep440_metadata() -> None:
    assert Version("0.1.0").serialize() == "0.1.0"
    assert Version("0.1.0").serialize(metadata=True) == "0.1.0"
    assert Version("0.1.0").serialize(metadata=False) == "0.1.0"

    assert Version("0.1.0", stage=("a", 1), commit="abc").serialize() == "0.1.0a1"
    assert Version("0.1.0", stage=("a", 1), commit="abc").serialize(metadata=True) == "0.1.0a1+abc"
    assert Version("0.1.0", stage=("a", 1), commit="abc").serialize(metadata=False) == "0.1.0a1"

    assert Version("0.1.0", distance=1, commit="abc").serialize() == "0.1.0.post1.dev0+abc"
    assert (
        Version("0.1.0", distance=1, commit="abc").serialize(metadata=True)
        == "0.1.0.post1.dev0+abc"
    )
    assert (
        Version("0.1.0", distance=1, commit="abc").serialize(metadata=False) == "0.1.0.post1.dev0"
    )

    assert (
        Version("0.1.0", distance=1, commit="abc", tagged_metadata="def").serialize(
            tagged_metadata=True
        )
        == "0.1.0.post1.dev0+def.abc"
    )


def test__version__serialize__semver_with_metadata() -> None:
    style = Style.SemVer
    assert Version("0.1.0").serialize(style=style) == "0.1.0"
    assert Version("0.1.0").serialize(metadata=True, style=style) == "0.1.0"
    assert Version("0.1.0").serialize(metadata=False, style=style) == "0.1.0"

    assert Version("0.1.0", stage=("a", 1), commit="abc").serialize(style=style) == "0.1.0-a.1"
    assert (
        Version("0.1.0", stage=("a", 1), commit="abc").serialize(metadata=True, style=style)
        == "0.1.0-a.1+abc"
    )
    assert (
        Version("0.1.0", stage=("a", 1), commit="abc").serialize(metadata=False, style=style)
        == "0.1.0-a.1"
    )

    assert Version("0.1.0", distance=1, commit="abc").serialize(style=style) == "0.1.0-post.1+abc"
    assert (
        Version("0.1.0", distance=1, commit="abc").serialize(metadata=True, style=style)
        == "0.1.0-post.1+abc"
    )
    assert (
        Version("0.1.0", distance=1, commit="abc").serialize(metadata=False, style=style)
        == "0.1.0-post.1"
    )

    assert (
        Version("0.1.0", distance=1, commit="abc", tagged_metadata="def").serialize(
            style=style, tagged_metadata=True
        )
        == "0.1.0-post.1+def.abc"
    )


def test__version__serialize__pvp_with_metadata() -> None:
    style = Style.Pvp
    assert Version("0.1.0").serialize(style=style) == "0.1.0"
    assert Version("0.1.0").serialize(metadata=True, style=style) == "0.1.0"
    assert Version("0.1.0").serialize(metadata=False, style=style) == "0.1.0"

    assert Version("0.1.0", stage=("a", 1), commit="abc").serialize(style=style) == "0.1.0-a-1"
    assert (
        Version("0.1.0", stage=("a", 1), commit="abc").serialize(metadata=True, style=style)
        == "0.1.0-a-1-abc"
    )
    assert (
        Version("0.1.0", stage=("a", 1), commit="abc").serialize(metadata=False, style=style)
        == "0.1.0-a-1"
    )

    assert Version("0.1.0", distance=1, commit="abc").serialize(style=style) == "0.1.0-post-1-abc"
    assert (
        Version("0.1.0", distance=1, commit="abc").serialize(metadata=True, style=style)
        == "0.1.0-post-1-abc"
    )
    assert (
        Version("0.1.0", distance=1, commit="abc").serialize(metadata=False, style=style)
        == "0.1.0-post-1"
    )

    assert (
        Version("0.1.0", distance=1, commit="abc", tagged_metadata="def").serialize(
            style=style, tagged_metadata=True
        )
        == "0.1.0-post-1-def-abc"
    )


def test__version__serialize__pep440_with_dirty() -> None:
    assert Version("0.1.0", dirty=True).serialize() == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(dirty=True) == "0.1.0+dirty"

    assert Version("0.1.0", dirty=False).serialize() == "0.1.0"
    assert Version("0.1.0", dirty=False).serialize(dirty=True) == "0.1.0"

    assert Version("0.1.0", dirty=True).serialize(metadata=True) == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(metadata=True, dirty=True) == "0.1.0+dirty"

    assert Version("0.1.0", dirty=True).serialize(metadata=False) == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(metadata=False, dirty=True) == "0.1.0"


def test__version__serialize__semver_with_dirty() -> None:
    style = Style.SemVer
    assert Version("0.1.0", dirty=True).serialize(style=style) == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(dirty=True, style=style) == "0.1.0+dirty"

    assert Version("0.1.0", dirty=False).serialize(style=style) == "0.1.0"
    assert Version("0.1.0", dirty=False).serialize(dirty=True, style=style) == "0.1.0"

    assert Version("0.1.0", dirty=True).serialize(metadata=True, style=style) == "0.1.0"
    assert (
        Version("0.1.0", dirty=True).serialize(metadata=True, dirty=True, style=style)
        == "0.1.0+dirty"
    )

    assert Version("0.1.0", dirty=True).serialize(metadata=False, style=style) == "0.1.0"
    assert (
        Version("0.1.0", dirty=True).serialize(metadata=False, dirty=True, style=style) == "0.1.0"
    )


def test__version__serialize__pvp_with_dirty() -> None:
    style = Style.Pvp
    assert Version("0.1.0", dirty=True).serialize(style=style) == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(dirty=True, style=style) == "0.1.0-dirty"

    assert Version("0.1.0", dirty=False).serialize(style=style) == "0.1.0"
    assert Version("0.1.0", dirty=False).serialize(dirty=True, style=style) == "0.1.0"

    assert Version("0.1.0", dirty=True).serialize(metadata=True, style=style) == "0.1.0"
    assert (
        Version("0.1.0", dirty=True).serialize(metadata=True, dirty=True, style=style)
        == "0.1.0-dirty"
    )

    assert Version("0.1.0", dirty=True).serialize(metadata=False, style=style) == "0.1.0"
    assert (
        Version("0.1.0", dirty=True).serialize(metadata=False, dirty=True, style=style) == "0.1.0"
    )


def test__version__serialize__format_as_str() -> None:
    format = (
        "{base},{stage},{revision},{distance},{commit},{dirty}"
        ",{branch},{branch_escaped},{timestamp}"
    )
    assert Version("0.1.0").serialize(format=format) == "0.1.0,,,0,,clean,,,"
    assert (
        Version(
            "1",
            stage=("a", 2),
            distance=3,
            commit="abc",
            dirty=True,
            branch="a/b",
            timestamp=dt.datetime(2001, 2, 3, 4, 5, 6, tzinfo=dt.timezone.utc),
        ).serialize(format=format)
        == "1,a,2,3,abc,dirty,a/b,ab,20010203040506"
    )
    with pytest.raises(ValueError):
        Version("0.1.0").serialize(format="v{base}", style=Style.Pep440)


def test__version__serialize__format_as_callable() -> None:
    def format(v: Version) -> str:
        return "{},{},{}".format(v.base, v.stage, v.revision)

    assert Version("0.1.0").serialize(format=format) == "0.1.0,None,None"
    assert Version("1", stage=("a", 2)).serialize(format=format) == "1,a,2"
    with pytest.raises(ValueError):
        Version("0.1.0").serialize(format=lambda v: "v{}".format(v.base), style=Style.Pep440)

    def immutable(v: Version) -> str:
        v.distance += 100
        return v.serialize()

    version = Version("0.1.0")
    version.serialize(format=immutable)
    assert version.distance == 0


def test__version__bump() -> None:
    assert Version("1.2.3").bump().serialize() == "1.2.4"
    assert Version("1.2.3").bump(-2).serialize() == "1.3.0"
    assert Version("1.2.3").bump(0).serialize() == "2.0.0"
    assert Version("1.2.3", stage=("a", None)).bump().serialize() == "1.2.3a2"
    assert Version("1.2.3", stage=("a", 4)).bump().serialize() == "1.2.3a5"


def test__version__parse():
    assert Version.parse("1.2.3") == Version("1.2.3")
    assert Version.parse("1.2.3a") == Version("1.2.3", stage=("a", None))
    assert Version.parse("1.2.3a3") == Version("1.2.3", stage=("a", 3))
    assert Version.parse("1.2.3+7") == Version("1.2.3", distance=7)
    assert Version.parse("1.2.3+d7") == Version("1.2.3", distance=7)
    assert Version.parse("1.2.3+b6a9020") == Version("1.2.3", commit="b6a9020")
    assert Version.parse("1.2.3+gb6a9020") == Version("1.2.3", commit="b6a9020")
    assert Version.parse("1.2.3+dirty") == Version("1.2.3", dirty=True)
    assert Version.parse("1.2.3+clean") == Version("1.2.3", dirty=False)
    assert Version.parse("1.2.3a3+7.b6a9020.dirty") == Version(
        "1.2.3", stage=("a", 3), distance=7, commit="b6a9020", dirty=True
    )
    assert Version.parse("1.2.3a3+7.b6a9020.dirty.linux") == Version(
        "1.2.3", stage=("a", 3), distance=7, commit="b6a9020", dirty=True, tagged_metadata="linux"
    )
    assert Version.parse("2!1.2.3") == Version("1.2.3", epoch=2)
    assert Version.parse("2!1.2.3a3+d7.gb6a9020.dirty.linux") == Version(
        "1.2.3",
        stage=("a", 3),
        distance=7,
        commit="b6a9020",
        dirty=True,
        tagged_metadata="linux",
        epoch=2,
    )

    assert Version.parse("foo") == Version("foo")

    assert Version.parse("1.2.3.dev5") == Version("1.2.3", distance=5)
    assert Version.parse("1.2.3.post4") == Version("1.2.3", stage=("post", 4))
    assert Version.parse("1.2.3.post4+d6") == Version("1.2.3", stage=("post", 4), distance=6)
    assert Version.parse("1.2.3.post4.dev5") == Version("1.2.3", distance=4)
    assert Version.parse("1.2.3.post4.dev5+d6") == Version("1.2.3", distance=10)
    assert Version.parse("1.2.3.post4.dev5.blah6") == Version("1.2.3.post4.dev5.blah6")


def test__get_version__from_name() -> None:
    assert get_version("dunamai") == Version(ilm.version("dunamai"))


def test__get_version__first_choice() -> None:
    assert get_version("dunamai", first_choice=lambda: Version("1")) == Version("1")


def test__get_version__third_choice() -> None:
    assert get_version("dunamai_nonexistent_test", third_choice=lambda: Version("3")) == Version(
        "3"
    )


def test__get_version__fallback() -> None:
    assert get_version("dunamai_nonexistent_test") == Version("0.0.0")


def test__get_version__from_name__ignore() -> None:
    assert get_version(
        "dunamai",
        ignore=[Version(ilm.version("dunamai"))],
        fallback=Version("2"),
    ) == Version("2")


def test__get_version__first_choice__ignore() -> None:
    assert get_version(
        "dunamai_nonexistent_test",
        first_choice=lambda: Version("1"),
        ignore=[Version("1")],
        fallback=Version("2"),
    ) == Version("2")


def test__get_version__first_choice__ignore_with_distance() -> None:
    assert get_version(
        "dunamai_nonexistent_test",
        first_choice=lambda: Version("1", distance=2),
        ignore=[Version("1")],
        fallback=Version("2"),
    ) == Version("2")
    assert get_version(
        "dunamai_nonexistent_test",
        first_choice=lambda: Version("1"),
        ignore=[Version("1", distance=2)],
        fallback=Version("2"),
    ) != Version("2")


def test__get_version__first_choice__ignore__with_commit() -> None:
    assert get_version(
        "dunamai_nonexistent_test",
        first_choice=lambda: Version("1", commit="aaaa"),
        ignore=[Version("1")],
        fallback=Version("2"),
    ) == Version("2")


def test__get_version__first_choice__ignore__without_commit() -> None:
    assert get_version(
        "dunamai_nonexistent_test",
        first_choice=lambda: Version("1"),
        ignore=[Version("1", commit="aaaa")],
        fallback=Version("2"),
    ) == Version("1")


def test__get_version__third_choice__ignore() -> None:
    assert get_version(
        "dunamai_nonexistent_test",
        third_choice=lambda: Version("3"),
        ignore=[Version("3")],
        fallback=Version("2"),
    ) == Version("2")


def test__version__from_any_vcs(tmp_path) -> None:
    with chdir(tmp_path):
        with pytest.raises(RuntimeError):
            Version.from_any_vcs()
        with pytest.raises(RuntimeError):
            Version.from_vcs(Vcs.Any)


def test__check_version__pep440() -> None:
    check_version("0.1.0")
    check_version("0.01.0")

    check_version("2!0.1.0")
    check_version("23!0.1.0")
    check_version("0.1.0a1")
    check_version("0.1.0b1")
    check_version("0.1.0rc1")
    with pytest.raises(ValueError):
        check_version("0.1.0x1")

    check_version("0.1.0.post0")
    check_version("0.1.0.dev0")
    check_version("0.1.0.post0.dev0")
    with pytest.raises(ValueError):
        check_version("0.1.0.other0")

    check_version("0.1.0+abc.dirty")
    check_version("0.1.0+abc..dirty")
    with pytest.raises(ValueError):
        check_version("0.1.0+abc_dirty")
    with pytest.raises(ValueError):
        check_version("0.1.0+.abc")
    with pytest.raises(ValueError):
        check_version("0.1.0+abc.")

    check_version("2!0.1.0a1.post0.dev0+abc.dirty")


def test__check_version__semver() -> None:
    style = Style.SemVer

    check_version("0.1.0", style=style)
    check_version("0.1.0-alpha.1", style=style)
    check_version("0.1.0+abc", style=style)
    check_version("0.1.0+a.b.c", style=style)
    check_version("0.1.0-alpha.1.beta.2+abc.dirty", style=style)

    with pytest.raises(ValueError):
        check_version("1", style=style)
    with pytest.raises(ValueError):
        check_version("0.1", style=style)
    with pytest.raises(ValueError):
        check_version("0.0.0.1", style=style)

    # "-" is a valid identifier.
    Version("0.1.0--").serialize(style=style)
    Version("0.1.0--.-").serialize(style=style)

    with pytest.raises(ValueError):
        check_version("0.1.0+abc_dirty", style=style)

    # No leading zeroes in numeric segments:
    with pytest.raises(ValueError):
        Version("00.0.0").serialize(style=style)
    with pytest.raises(ValueError):
        Version("0.01.0").serialize(style=style)
    with pytest.raises(ValueError):
        Version("0.1.0-alpha.02").serialize(style=style)
    # But leading zeroes are fine for non-numeric parts:
    Version("0.1.0-alpha.02a").serialize(style=style)

    # Identifiers can't be empty:
    with pytest.raises(ValueError):
        Version("0.1.0-.").serialize(style=style)
    with pytest.raises(ValueError):
        Version("0.1.0-a.").serialize(style=style)
    with pytest.raises(ValueError):
        Version("0.1.0-.a").serialize(style=style)


def test__check_version__pvp() -> None:
    style = Style.Pvp

    check_version("1", style=style)
    check_version("0.1", style=style)
    check_version("0.0.1", style=style)
    check_version("0.0.0.1", style=style)
    check_version("0.1.0-alpha-1", style=style)

    with pytest.raises(ValueError):
        check_version("0.1.0-a.1", style=style)
    with pytest.raises(ValueError):
        check_version("0.1.0-abc_dirty", style=style)


def test__default_version_pattern() -> None:
    def check_re(
        tag: str,
        base: Optional[str] = None,
        stage: Optional[str] = None,
        revision: Optional[str] = None,
        tagged_metadata: Optional[str] = None,
        epoch: Optional[str] = None,
    ) -> None:
        result = re.search(VERSION_SOURCE_PATTERN, tag)
        if result is None:
            if any(x is not None for x in [base, stage, revision]):
                raise ValueError("Pattern did not match, {tag}".format(tag=tag))
        else:
            assert result.group("base") == base
            assert result.group("stage") == stage
            assert result.group("revision") == revision
            assert result.group("tagged_metadata") == tagged_metadata
            assert result.group("epoch") == epoch

    check_re("v0.1.0", "0.1.0")
    check_re("av0.1.0")

    check_re("v0.1.0a", "0.1.0", "a")
    check_re("v0.1.0a1", "0.1.0", "a", "1")
    check_re("v0.1.0a1b", None)
    check_re("v0.1.0-1.a", None)

    check_re("v0.1.0-alpha.123", "0.1.0", "alpha", "123")
    check_re("v0.1.0-1.alpha", None)
    check_re("v0.1.0-alpha.1.post.4", None)

    check_re("v0.1.0rc.4", "0.1.0", "rc", "4")
    check_re("v0.1.0-beta", "0.1.0", "beta")

    check_re("v0.1.0a2", "0.1.0", "a", "2")
    check_re("v0.1.0-a-2", "0.1.0", "a", "2")
    check_re("v0.1.0.a.2", "0.1.0", "a", "2")
    check_re("v0.1.0_a_2", "0.1.0", "a", "2")

    check_re("v0.1.0rc.4+specifier", "0.1.0", "rc", "4", tagged_metadata="specifier")

    check_re("v1", "1")
    check_re("v1b2", "1", "b", "2")

    check_re("v1!2", "2", epoch="1")


def test__serialize_pep440():
    assert serialize_pep440("1.2.3") == "1.2.3"
    assert serialize_pep440("1.2.3", epoch=0) == "0!1.2.3"
    assert serialize_pep440("1.2.3", stage="a") == "1.2.3a0"
    assert serialize_pep440("1.2.3", stage="a", revision=4) == "1.2.3a4"
    assert serialize_pep440("1.2.3", post=4) == "1.2.3.post4"
    assert serialize_pep440("1.2.3", dev=4) == "1.2.3.dev4"
    assert serialize_pep440("1.2.3", metadata=[]) == "1.2.3"
    assert serialize_pep440("1.2.3", metadata=["foo"]) == "1.2.3+foo"
    assert serialize_pep440("1.2.3", metadata=["foo", "bar"]) == "1.2.3+foo.bar"
    assert serialize_pep440("1.2.3", metadata=[4]) == "1.2.3+4"

    assert (
        serialize_pep440(
            "1.2.3", epoch=0, stage="a", revision=4, post=5, dev=6, metadata=["foo", "bar"]
        )
        == "0!1.2.3a4.post5.dev6+foo.bar"
    )

    assert serialize_pep440("1.2.3", stage="alpha", revision=4) == "1.2.3a4"
    assert serialize_pep440("1.2.3", stage="ALphA", revision=4) == "1.2.3a4"
    assert serialize_pep440("1.2.3", stage="beta", revision=4) == "1.2.3b4"
    assert serialize_pep440("1.2.3", stage="c", revision=4) == "1.2.3rc4"
    assert serialize_pep440("1.2.3", stage="pre", revision=4) == "1.2.3rc4"
    assert serialize_pep440("1.2.3", stage="preview", revision=4) == "1.2.3rc4"

    with pytest.raises(ValueError):
        serialize_pep440("foo")


def test__serialize_semver():
    assert serialize_semver("1.2.3") == "1.2.3"
    assert serialize_semver("1.2.3", pre=["alpha"]) == "1.2.3-alpha"
    assert serialize_semver("1.2.3", pre=["alpha", 4]) == "1.2.3-alpha.4"
    assert serialize_semver("1.2.3", metadata=["foo"]) == "1.2.3+foo"
    assert serialize_semver("1.2.3", metadata=["foo", "bar"]) == "1.2.3+foo.bar"
    assert serialize_semver("1.2.3", metadata=[4]) == "1.2.3+4"

    assert (
        serialize_semver("1.2.3", pre=["alpha", 4], metadata=["foo", "bar"])
        == "1.2.3-alpha.4+foo.bar"
    )

    with pytest.raises(ValueError):
        serialize_semver("foo")


def test__serialize_pvp():
    assert serialize_pvp("1") == "1"
    assert serialize_pvp("1.2") == "1.2"
    assert serialize_pvp("1.2.3") == "1.2.3"
    assert serialize_pvp("1.2.3.4") == "1.2.3.4"
    assert serialize_pvp("1.2.3", metadata=["foo"]) == "1.2.3-foo"
    assert serialize_pvp("1.2.3", metadata=["foo", "bar"]) == "1.2.3-foo-bar"
    assert serialize_pvp("1.2.3", metadata=[4]) == "1.2.3-4"

    with pytest.raises(ValueError):
        serialize_pvp("foo")


def test__bump_version():
    # default bump=1
    assert bump_version("1.2.3") == "1.2.4"

    assert bump_version("1.2.3", 0) == "2.0.0"
    assert bump_version("1.2.3", 1) == "1.3.0"
    assert bump_version("1.2.3", 2) == "1.2.4"

    assert bump_version("1.2.3", -1) == "1.2.4"
    assert bump_version("1.2.3", -2) == "1.3.0"
    assert bump_version("1.2.3", -3) == "2.0.0"

    # expicit bump increment
    assert bump_version("1.2.3", increment=3) == "1.2.6"

    assert bump_version("1.2.3", 0, increment=3) == "4.0.0"
    assert bump_version("1.2.3", 1, increment=3) == "1.5.0"
    assert bump_version("1.2.3", 2, increment=3) == "1.2.6"

    assert bump_version("1.2.3", -1, increment=3) == "1.2.6"
    assert bump_version("1.2.3", -2, increment=3) == "1.5.0"
    assert bump_version("1.2.3", -3, increment=3) == "4.0.0"

    # check if incorrect index raises issues
    with pytest.raises(IndexError):
        bump_version("1.2.3", 3)

    with pytest.raises(IndexError):
        bump_version("1.2.3", -4)

    with pytest.raises(ValueError):
        bump_version("foo", 0)
