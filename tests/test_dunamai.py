import pkg_resources
from unittest import mock

import pytest

from dunamai import get_version, Version


def test__version__init():
    v = Version("1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True)
    assert v.base == "1"
    assert v.epoch == 2
    assert v.pre_type == "a"
    assert v.pre_number == 3
    assert v.post == 4
    assert v.dev == 5
    assert v.commit == "abc"
    assert v.dirty

    with pytest.raises(ValueError):
        Version("1", pre=("x", 3))


def test__version__str():
    v = Version(
        "1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True,
    )
    assert str(v) == v.serialize()


def test__version__repr():
    v = Version(
        "1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True,
    )
    assert repr(v) == (
        "Version(base='1', epoch=2, pre_type='a', pre_number=3,"
        " post=4, dev=5, commit='abc', dirty=True)"
    )


def test__version__ordering():
    Version("0.1.0", post=3, dev=0) == Version("0.1.0", post=3, dev=0)
    Version("1.0.0", epoch=2) > Version("2.0.0", epoch=1)
    with pytest.raises(TypeError):
        Version("0.1.0") == "0.1.0"
    with pytest.raises(TypeError):
        Version("0.1.0") < "0.2.0"


def test__version__serialize():
    assert Version("0.1.0").serialize() == "0.1.0"

    assert Version(
        "1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True,
    ).serialize() == "2!1a3.post4.dev5+abc"
    assert Version(
        "1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True,
    ).serialize(with_dirty=True) == "2!1a3.post4.dev5+abc.dirty"
    assert Version(
        "1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True,
    ).serialize(with_metadata=False) == "2!1a3.post4.dev5"
    assert Version(
        "1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True,
    ).serialize(with_metadata=False, with_dirty=True) == "2!1a3.post4.dev5"

    assert Version(
        "1", epoch=0, pre=("a", 0), post=0, dev=0, commit="000", dirty=False,
    ).serialize() == "0!1a0.post0.dev0+000"

    assert Version("1", pre=("b", 3)).serialize() == "1b3"
    assert Version("1", pre=("rc", 3)).serialize() == "1rc3"


def test__version__serialize__with_metadata():
    assert Version("0.1.0").serialize() == "0.1.0"
    assert Version("0.1.0").serialize(with_metadata=True) == "0.1.0"
    assert Version("0.1.0").serialize(with_metadata=False) == "0.1.0"

    assert Version("0.1.0", post=1, commit="abc").serialize() == "0.1.0.post1+abc"
    assert Version("0.1.0", post=1, commit="abc").serialize(with_metadata=True) == "0.1.0.post1+abc"
    assert Version("0.1.0", post=1, commit="abc").serialize(with_metadata=False) == "0.1.0.post1"

    assert Version("0.1.0", dev=1, commit="abc").serialize() == "0.1.0.dev1+abc"
    assert Version("0.1.0", dev=1, commit="abc").serialize(with_metadata=True) == "0.1.0.dev1+abc"
    assert Version("0.1.0", dev=1, commit="abc").serialize(with_metadata=False) == "0.1.0.dev1"


def test__version__serialize__with_dirty():
    assert Version("0.1.0", dirty=True).serialize() == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(with_dirty=True) == "0.1.0+dirty"

    assert Version("0.1.0", dirty=False).serialize() == "0.1.0"
    assert Version("0.1.0", dirty=False).serialize(with_dirty=True) == "0.1.0"

    assert Version("0.1.0", dirty=True).serialize(with_metadata=True) == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(with_metadata=True, with_dirty=True) == "0.1.0+dirty"

    assert Version("0.1.0", dirty=True).serialize(with_metadata=False) == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(with_metadata=False, with_dirty=True) == "0.1.0"

    assert Version("0.1.0", post=1, dirty=True).serialize() == "0.1.0.post1"
    assert Version("0.1.0", post=1, dirty=True).serialize(with_dirty=True) == "0.1.0.post1+dirty"


def test__version__serialize__error_conditions():
    with pytest.raises(ValueError):
        Version("x").serialize()
    with pytest.raises(ValueError):
        v = Version("1", pre=("a", 3))
        v.pre_type = "x"
        v.serialize()


@mock.patch("dunamai._run_cmd")
def test__version__from_git__4_parts_with_distance_and_with_dirty(run):
    run.return_value = (0, "v0.1.0rc5-44-g644252b-dirty")
    v = Version.from_git()
    assert v.base == "0.1.0"
    assert v.epoch is None
    assert v.pre_type == "rc"
    assert v.pre_number == 5
    assert v.post == 44
    assert v.dev == 0
    assert v.commit == "g644252b"
    assert v.dirty


@mock.patch("dunamai._run_cmd")
def test__version__from_git__4_parts_without_distance(run):
    run.return_value = (0, "v0.1.0rc5-0-g644252b-dirty")
    v = Version.from_git()
    assert v.base == "0.1.0"
    assert v.epoch is None
    assert v.pre_type == "rc"
    assert v.pre_number == 5
    assert v.post is None
    assert v.dev is None
    assert v.commit == "g644252b"
    assert v.dirty


@mock.patch("dunamai._run_cmd")
def test__version__from_git__3_parts(run):
    run.return_value = (0, "v0.1.0rc5-44-g644252b")
    v = Version.from_git()
    assert v.base == "0.1.0"
    assert v.pre_type == "rc"
    assert v.pre_number == 5
    assert v.post == 44
    assert v.dev == 0
    assert v.commit == "g644252b"
    assert not v.dirty


@mock.patch("dunamai._run_cmd")
def test__version__from_git__2_parts(run):
    run.side_effect = [(128, ""), (0, "g644252b-dirty")]
    v = Version.from_git()
    assert v.base == "0.0.0"
    assert v.post == 0
    assert v.dev == 0
    assert v.commit == "g644252b"
    assert v.dirty


@mock.patch("dunamai._run_cmd")
def test__version__from_git__1_part(run):
    run.side_effect = [(128, ""), (0, "g644252b")]
    v = Version.from_git()
    assert v.base == "0.0.0"
    assert v.post == 0
    assert v.dev == 0
    assert v.commit == "g644252b"
    assert not v.dirty


@mock.patch("dunamai._run_cmd")
def test__version__from_git__fallback(run):
    run.side_effect = [(128, ""), (128, "")]
    v = Version.from_git()
    assert v.base == "0.0.0"
    assert v.post == 0
    assert v.dev == 0
    assert v.commit == "initial"


@mock.patch("dunamai._run_cmd")
def test__version__from_git__first_git_error(run):
    with pytest.raises(RuntimeError):
        run.return_value = (1, "")
        Version.from_git()


@mock.patch("dunamai._run_cmd")
def test__version__from_git__second_git_error(run):
    with pytest.raises(RuntimeError):
        run.side_effect = [(128, ""), (1, "")]
        Version.from_git()


@mock.patch("dunamai._run_cmd")
def test__version__from_git__no_pattern_match(run):
    with pytest.raises(ValueError):
        run.return_value = (0, "v___0.1.0rc5-44-g644252b")
        Version.from_git()


@mock.patch("dunamai._run_cmd")
def test__version__from_git__no_base_group(run):
    with pytest.raises(ValueError):
        run.return_value = (0, "v0.1.0rc5-44-g644252b")
        Version.from_git(r"v(\d+\.\d+\.\d+)")


@mock.patch("dunamai._run_cmd")
def test__version__from_git__no_pre_groups(run):
    run.return_value = (0, "v0.1.0-44-g644252b")
    v = Version.from_git(r"v(?P<base>\d+\.\d+\.\d+)")
    assert v.base == "0.1.0"
    assert v.pre_type is None
    assert v.pre_number is None


def test__get_version__from_name():
    assert get_version("dunamai") == Version(pkg_resources.get_distribution("dunamai").version)


def test__get_version__first_choice():
    assert get_version("dunamai", first_choice=lambda: Version("1")) == Version("1")


def test__get_version__third_choice():
    assert get_version("dunamai_nonexistent_test", third_choice=lambda: Version("3")) == Version("3")


def test__get_version__fallback():
    assert get_version("dunamai_nonexistent_test") == Version("0.0.0")
