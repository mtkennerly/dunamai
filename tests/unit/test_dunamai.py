import os
import pkg_resources
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional

import pytest

from dunamai import (
    bump_version,
    check_version,
    get_version,
    Version,
    serialize_pep440,
    serialize_pvp,
    serialize_semver,
    Style,
    Vcs,
    _run_cmd,
    _VERSION_PATTERN,
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


def test__version__init() -> None:
    v = Version("1", stage=("a", 2), distance=3, commit="abc", dirty=True)
    assert v.base == "1"
    assert v.stage == "a"
    assert v.revision == 2
    assert v.distance == 3
    assert v.commit == "abc"
    assert v.dirty


def test__version__str() -> None:
    v = Version("1", stage=("a", 2), distance=3, commit="abc", dirty=True)
    assert str(v) == v.serialize()


def test__version__repr() -> None:
    v = Version("1", stage=("a", 2), distance=3, commit="abc", dirty=True)
    assert repr(v) == (
        "Version(base='1', stage='a', revision=2, distance=3, commit='abc', dirty=True)"
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


def test__version__serialize__format() -> None:
    format = "{base},{stage},{revision},{distance},{commit},{dirty}"
    assert Version("0.1.0").serialize(format=format) == "0.1.0,,,0,,clean"
    assert (
        Version("1", stage=("a", 2), distance=3, commit="abc", dirty=True).serialize(format=format)
        == "1,a,2,3,abc,dirty"
    )
    with pytest.raises(ValueError):
        Version("0.1.0").serialize(format="v{base}", style=Style.Pep440)


def test__get_version__from_name() -> None:
    assert get_version("dunamai") == Version(pkg_resources.get_distribution("dunamai").version)


def test__get_version__first_choice() -> None:
    assert get_version("dunamai", first_choice=lambda: Version("1")) == Version("1")


def test__get_version__third_choice() -> None:
    assert get_version("dunamai_nonexistent_test", third_choice=lambda: Version("3")) == Version(
        "3"
    )


def test__get_version__fallback() -> None:
    assert get_version("dunamai_nonexistent_test") == Version("0.0.0")


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

    check_version("2!0.1.0a1.post0.dev0+abc.dirty")


def test__check_version__semver() -> None:
    style = Style.SemVer

    check_version("0.1.0", style=style)
    check_version("0.1.0-alpha.1", style=style)
    check_version("0.1.0+abc", style=style)
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


def test__default_version_pattern() -> None:
    def check_re(tag: str, base: str = None, stage: str = None, revision: str = None) -> None:
        result = re.search(_VERSION_PATTERN, tag)
        if result is None:
            if any(x is not None for x in [base, stage, revision]):
                raise ValueError("Pattern did not match")
        else:
            assert result.group("base") == base
            assert result.group("stage") == stage
            assert result.group("revision") == revision

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
    assert bump_version("1.2.3") == "1.2.4"

    assert bump_version("1.2.3", 0) == "2.0.0"
    assert bump_version("1.2.3", 1) == "1.3.0"
    assert bump_version("1.2.3", 2) == "1.2.4"

    assert bump_version("1.2.3", -1) == "1.2.4"
    assert bump_version("1.2.3", -2) == "1.3.0"
    assert bump_version("1.2.3", -3) == "2.0.0"

    with pytest.raises(IndexError):
        bump_version("1.2.3", 3)

    with pytest.raises(IndexError):
        bump_version("1.2.3", -4)

    with pytest.raises(ValueError):
        bump_version("foo", 0)
