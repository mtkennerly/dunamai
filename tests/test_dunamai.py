import os
import pkg_resources
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional

import pytest

from dunamai import check_version, get_version, Version, Style, _run_cmd


@contextmanager
def chdir(where: Path) -> Iterator[None]:
    start = Path.cwd()
    os.chdir(str(where))
    try:
        yield
    finally:
        os.chdir(str(start))


def make_run_callback(where: Path) -> Callable:
    def inner(command, expected_code=0):
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


def test__version__str():
    v = Version("1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True)
    assert str(v) == v.serialize()


def test__version__repr():
    v = Version("1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True)
    assert repr(v) == (
        "Version(base='1', epoch=2, pre_type='a', pre_number=3,"
        " post=4, dev=5, commit='abc', dirty=True)"
    )


def test__version__ordering():
    assert Version("0.1.0", post=3, dev=0) == Version("0.1.0", post=3, dev=0)
    assert Version("1.0.0", epoch=2) > Version("2.0.0", epoch=1)
    with pytest.raises(TypeError):
        Version("0.1.0") == "0.1.0"
    with pytest.raises(TypeError):
        Version("0.1.0") < "0.2.0"
    assert Version("0.1.0", commit="a") != Version("0.1.0", commit="b")
    assert Version("0.1.0", dirty=True) == Version("0.1.0", dirty=True)
    assert Version("0.1.0", dirty=False) != Version("0.1.0", dirty=True)
    assert Version("0.1.0") != Version("0.1.0", dirty=True)
    assert Version("0.1.0") != Version("0.1.0", dirty=False)


def test__version__serialize__pep440():
    assert Version("0.1.0").serialize() == "0.1.0"

    assert (
        Version("1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True).serialize()
        == "2!1a3.post4.dev5+abc"
    )
    assert (
        Version("1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True).serialize(
            dirty=True
        )
        == "2!1a3.post4.dev5+abc.dirty"
    )
    assert (
        Version("1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True).serialize(
            metadata=False
        )
        == "2!1a3.post4.dev5"
    )
    assert (
        Version("1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True).serialize(
            metadata=False, dirty=True
        )
        == "2!1a3.post4.dev5"
    )

    assert (
        Version("1", epoch=0, pre=("a", 0), post=0, dev=0, commit="000", dirty=False).serialize()
        == "0!1a0.post0.dev0+000"
    )

    assert Version("1", pre=("b", 3)).serialize() == "1b3"
    assert Version("1", pre=("rc", 3)).serialize() == "1rc3"


def test__version__serialize__semver():
    style = Style.SemVer
    assert Version("0.1.0").serialize(style=style) == "0.1.0"

    assert (
        Version(
            "0.1.0", epoch=2, pre=("alpha", 3), post=4, dev=5, commit="abc", dirty=True
        ).serialize(style=style)
        == "0.1.0-epoch.2.alpha.3.post.4.dev.5+abc"
    )
    assert (
        Version(
            "0.1.0", epoch=2, pre=("alpha", 3), post=4, dev=5, commit="abc", dirty=True
        ).serialize(dirty=True, style=style)
        == "0.1.0-epoch.2.alpha.3.post.4.dev.5+abc.dirty"
    )
    assert (
        Version(
            "0.1.0", epoch=2, pre=("alpha", 3), post=4, dev=5, commit="abc", dirty=True
        ).serialize(metadata=False, style=style)
        == "0.1.0-epoch.2.alpha.3.post.4.dev.5"
    )
    assert (
        Version(
            "0.1.0", epoch=2, pre=("alpha", 3), post=4, dev=5, commit="abc", dirty=True
        ).serialize(metadata=False, dirty=True, style=style)
        == "0.1.0-epoch.2.alpha.3.post.4.dev.5"
    )

    assert (
        Version(
            "0.1.0", epoch=0, pre=("alpha", 0), post=0, dev=0, commit="000", dirty=False
        ).serialize(style=style)
        == "0.1.0-epoch.0.alpha.0.post.0.dev.0+000"
    )

    assert Version("0.1.0", pre=("beta", 3)).serialize(style=style) == "0.1.0-beta.3"
    assert Version("0.1.0", pre=("rc", 3)).serialize(style=style) == "0.1.0-rc.3"


def test__version__serialize__pvp():
    style = Style.Pvp
    assert Version("0.1.0").serialize(style=style) == "0.1.0"

    assert (
        Version(
            "0.1.0", epoch=2, pre=("alpha", 3), post=4, dev=5, commit="abc", dirty=True
        ).serialize(style=style)
        == "0.1.0-epoch-2-alpha-3-post-4-dev-5-abc"
    )
    assert (
        Version(
            "0.1.0", epoch=2, pre=("alpha", 3), post=4, dev=5, commit="abc", dirty=True
        ).serialize(dirty=True, style=style)
        == "0.1.0-epoch-2-alpha-3-post-4-dev-5-abc-dirty"
    )
    assert (
        Version(
            "0.1.0", epoch=2, pre=("alpha", 3), post=4, dev=5, commit="abc", dirty=True
        ).serialize(metadata=False, style=style)
        == "0.1.0-epoch-2-alpha-3-post-4-dev-5"
    )
    assert (
        Version(
            "0.1.0", epoch=2, pre=("alpha", 3), post=4, dev=5, commit="abc", dirty=True
        ).serialize(metadata=False, dirty=True, style=style)
        == "0.1.0-epoch-2-alpha-3-post-4-dev-5"
    )

    assert (
        Version(
            "0.1.0", epoch=0, pre=("alpha", 0), post=0, dev=0, commit="000", dirty=False
        ).serialize(style=style)
        == "0.1.0-epoch-0-alpha-0-post-0-dev-0-000"
    )

    assert Version("0.1.0", pre=("beta", 3)).serialize(style=style) == "0.1.0-beta-3"
    assert Version("0.1.0", pre=("rc", 3)).serialize(style=style) == "0.1.0-rc-3"


def test__version__serialize__pep440_metadata():
    assert Version("0.1.0").serialize() == "0.1.0"
    assert Version("0.1.0").serialize(metadata=True) == "0.1.0"
    assert Version("0.1.0").serialize(metadata=False) == "0.1.0"

    assert Version("0.1.0", pre=("a", 1), commit="abc").serialize() == "0.1.0a1"
    assert Version("0.1.0", pre=("a", 1), commit="abc").serialize(metadata=True) == "0.1.0a1+abc"
    assert Version("0.1.0", pre=("a", 1), commit="abc").serialize(metadata=False) == "0.1.0a1"

    assert Version("0.1.0", post=1, commit="abc").serialize() == "0.1.0.post1+abc"
    assert Version("0.1.0", post=1, commit="abc").serialize(metadata=True) == "0.1.0.post1+abc"
    assert Version("0.1.0", post=1, commit="abc").serialize(metadata=False) == "0.1.0.post1"

    assert Version("0.1.0", dev=1, commit="abc").serialize() == "0.1.0.dev1+abc"
    assert Version("0.1.0", dev=1, commit="abc").serialize(metadata=True) == "0.1.0.dev1+abc"
    assert Version("0.1.0", dev=1, commit="abc").serialize(metadata=False) == "0.1.0.dev1"


def test__version__serialize__semver_with_metadata():
    style = Style.SemVer
    assert Version("0.1.0").serialize(style=style) == "0.1.0"
    assert Version("0.1.0").serialize(metadata=True, style=style) == "0.1.0"
    assert Version("0.1.0").serialize(metadata=False, style=style) == "0.1.0"

    assert Version("0.1.0", pre=("a", 1), commit="abc").serialize(style=style) == "0.1.0-a.1"
    assert (
        Version("0.1.0", pre=("a", 1), commit="abc").serialize(metadata=True, style=style)
        == "0.1.0-a.1+abc"
    )
    assert (
        Version("0.1.0", pre=("a", 1), commit="abc").serialize(metadata=False, style=style)
        == "0.1.0-a.1"
    )

    assert Version("0.1.0", post=1, commit="abc").serialize(style=style) == "0.1.0-post.1+abc"
    assert (
        Version("0.1.0", post=1, commit="abc").serialize(metadata=True, style=style)
        == "0.1.0-post.1+abc"
    )
    assert (
        Version("0.1.0", post=1, commit="abc").serialize(metadata=False, style=style)
        == "0.1.0-post.1"
    )

    assert Version("0.1.0", dev=1, commit="abc").serialize(style=style) == "0.1.0-dev.1+abc"
    assert (
        Version("0.1.0", dev=1, commit="abc").serialize(metadata=True, style=style)
        == "0.1.0-dev.1+abc"
    )
    assert (
        Version("0.1.0", dev=1, commit="abc").serialize(metadata=False, style=style)
        == "0.1.0-dev.1"
    )


def test__version__serialize__pvp_with_metadata():
    style = Style.Pvp
    assert Version("0.1.0").serialize(style=style) == "0.1.0"
    assert Version("0.1.0").serialize(metadata=True, style=style) == "0.1.0"
    assert Version("0.1.0").serialize(metadata=False, style=style) == "0.1.0"

    assert Version("0.1.0", pre=("a", 1), commit="abc").serialize(style=style) == "0.1.0-a-1"
    assert (
        Version("0.1.0", pre=("a", 1), commit="abc").serialize(metadata=True, style=style)
        == "0.1.0-a-1-abc"
    )
    assert (
        Version("0.1.0", pre=("a", 1), commit="abc").serialize(metadata=False, style=style)
        == "0.1.0-a-1"
    )

    assert Version("0.1.0", post=1, commit="abc").serialize(style=style) == "0.1.0-post-1-abc"
    assert (
        Version("0.1.0", post=1, commit="abc").serialize(metadata=True, style=style)
        == "0.1.0-post-1-abc"
    )
    assert (
        Version("0.1.0", post=1, commit="abc").serialize(metadata=False, style=style)
        == "0.1.0-post-1"
    )

    assert Version("0.1.0", dev=1, commit="abc").serialize(style=style) == "0.1.0-dev-1-abc"
    assert (
        Version("0.1.0", dev=1, commit="abc").serialize(metadata=True, style=style)
        == "0.1.0-dev-1-abc"
    )
    assert (
        Version("0.1.0", dev=1, commit="abc").serialize(metadata=False, style=style)
        == "0.1.0-dev-1"
    )


def test__version__serialize__pep440_with_dirty():
    assert Version("0.1.0", dirty=True).serialize() == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(dirty=True) == "0.1.0+dirty"

    assert Version("0.1.0", dirty=False).serialize() == "0.1.0"
    assert Version("0.1.0", dirty=False).serialize(dirty=True) == "0.1.0"

    assert Version("0.1.0", dirty=True).serialize(metadata=True) == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(metadata=True, dirty=True) == "0.1.0+dirty"

    assert Version("0.1.0", dirty=True).serialize(metadata=False) == "0.1.0"
    assert Version("0.1.0", dirty=True).serialize(metadata=False, dirty=True) == "0.1.0"


def test__version__serialize__semver_with_dirty():
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


def test__version__serialize__pvp_with_dirty():
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


def test__version__serialize__format():
    format = "{epoch},{base},{pre_type},{pre_number},{post},{dev},{commit},{dirty}"
    assert Version("0.1.0").serialize(format=format) == ",0.1.0,,,,,,clean"
    assert (
        Version("1", epoch=2, pre=("a", 3), post=4, dev=5, commit="abc", dirty=True).serialize(
            format=format
        )
        == "2,1,a,3,4,5,abc,dirty"
    )
    with pytest.raises(ValueError):
        Version("0.1.0").serialize(format="v{base}", style=Style.Pep440)


def test__get_version__from_name():
    assert get_version("dunamai") == Version(pkg_resources.get_distribution("dunamai").version)


def test__get_version__first_choice():
    assert get_version("dunamai", first_choice=lambda: Version("1")) == Version("1")


def test__get_version__third_choice():
    assert get_version("dunamai_nonexistent_test", third_choice=lambda: Version("3")) == Version(
        "3"
    )


def test__get_version__fallback():
    assert get_version("dunamai_nonexistent_test") == Version("0.0.0")


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires Git")
def test__version__from_git(tmp_path):
    vcs = tmp_path / "dunamai-git"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_git)

    with chdir(vcs):
        run("git init")
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit=None, dirty=True)

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit=None, dirty=True)

        run("git add .")
        run('git commit -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit="abc", dirty=False)

        run("git tag v0.1.0")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="abc", dirty=False)
        assert run("dunamai from git") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        # Additional one-off checks not in other VCS integration tests:
        assert run(r'dunamai from any --pattern "(?P<base>\d\.\d\.\d)"') == "0.1.0"
        run(r'dunamai from any --pattern "(\d\.\d\.\d)"', 1)
        assert run('dunamai from any --format "v{base}"') == "v0.1.0"
        assert run('dunamai from any --style "semver"') == "0.1.0"
        assert (
            run('dunamai from any --format "v{base}" --style "semver"', 1)
            == "Version 'v0.1.0' does not conform to the Semantic Versioning style"
        )
        assert run("dunamai from any --latest-tag") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=True)

        run("git add .")
        run('git commit -m "Second"')
        assert from_vcs() == Version("0.1.0", post=1, dev=0, commit="abc", dirty=False)
        assert from_any_vcs() == Version("0.1.0", post=1, dev=0, commit="abc", dirty=False)

        run("git tag unmatched")
        assert from_vcs() == Version("0.1.0", post=1, dev=0, commit="abc", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)


@pytest.mark.skipif(shutil.which("hg") is None, reason="Requires Mercurial")
def test__version__from_mercurial(tmp_path):
    vcs = tmp_path / "dunamai-hg"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_mercurial)

    with chdir(vcs):
        run("hg init")
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit=None, dirty=False)

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit=None, dirty=True)

        run("hg add .")
        run('hg commit -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit="abc", dirty=False)

        run("hg tag v0.1.0")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="abc", dirty=False)
        assert run("dunamai from mercurial") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=True)

        run("hg add .")
        run('hg commit -m "Second"')
        assert from_vcs() == Version("0.1.0", post=1, dev=0, commit="abc", dirty=False)
        assert from_any_vcs() == Version("0.1.0", post=1, dev=0, commit="abc", dirty=False)

        run("hg tag unmatched")
        assert from_vcs() == Version("0.1.0", post=2, dev=0, commit="abc", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)


@pytest.mark.skipif(shutil.which("darcs") is None, reason="Requires Darcs")
def test__version__from_darcs(tmp_path):
    vcs = tmp_path / "dunamai-darcs"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_darcs)

    with chdir(vcs):
        run("darcs init")
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit=None, dirty=False)

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit=None, dirty=True)

        run("darcs add foo.txt")
        run('darcs record -am "Initial commit"')
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit="abc", dirty=False)

        run("darcs tag v0.1.0")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="abc", dirty=False)
        assert run("dunamai from darcs") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=True)

        run('darcs record -am "Second"')
        assert from_vcs() == Version("0.1.0", post=1, dev=0, commit="abc", dirty=False)
        assert from_any_vcs() == Version("0.1.0", post=1, dev=0, commit="abc", dirty=False)

        run("darcs tag unmatched")
        assert from_vcs() == Version("0.1.0", post=2, dev=0, commit="abc", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)


@pytest.mark.skipif(
    None in [shutil.which("svn"), shutil.which("svnadmin")], reason="Requires Subversion"
)
def test__version__from_subversion(tmp_path):
    vcs = tmp_path / "dunamai-svn"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_subversion, mock_commit=None)

    vcs_srv = tmp_path / "dunamai-svn-srv"
    vcs_srv.mkdir()
    run_srv = make_run_callback(vcs_srv)
    vcs_srv_uri = vcs_srv.as_uri()

    with chdir(vcs_srv):
        run_srv("svnadmin create .")

    with chdir(vcs):
        run('svn checkout "{}" .'.format(vcs_srv_uri))
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit=None, dirty=False)

        run("svn mkdir trunk tags")
        (vcs / "trunk" / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit=None, dirty=True)

        run("svn add --force .")
        run('svn commit -m "Initial commit"')
        run("svn update")
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit="1", dirty=False)

        run('svn copy {0}/trunk {0}/tags/v0.1.0 -m "Tag 1"'.format(vcs_srv_uri))
        run("svn update")
        assert from_vcs() == Version("0.1.0", commit="2", dirty=False)
        assert run("dunamai from subversion") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "trunk" / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="2", dirty=True)

        run('svn commit -m "Second"')
        run("svn update")
        assert from_vcs() == Version("0.1.0", post=1, dev=0, commit="3", dirty=False)
        assert from_any_vcs_unmocked() == Version("0.1.0", post=1, dev=0, commit="3", dirty=False)

        # Ensure we get the tag based on the highest commit, not necessarily
        # just the newest tag.
        run('svn copy {0}/trunk {0}/tags/v0.2.0 -m "Tag 2"'.format(vcs_srv_uri))  # commit 4
        run('svn copy {0}/trunk {0}/tags/v0.1.1 -r 1 -m "Tag 3"'.format(vcs_srv_uri))  # commit 5
        run("svn update")
        assert from_vcs() == Version("0.2.0", post=1, dev=0, commit="5", dirty=False)

        run('svn copy {0}/trunk {0}/tags/unmatched -m "Tag 3"'.format(vcs_srv_uri))  # commit 6
        run("svn update")
        assert from_vcs() == Version("0.2.0", post=2, dev=0, commit="6", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)


@pytest.mark.skipif(shutil.which("bzr") is None, reason="Requires Bazaar")
def test__version__from_bazaar(tmp_path):
    vcs = tmp_path / "dunamai-bzr"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_bazaar, mock_commit=None)

    with chdir(vcs):
        run("bzr init")
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit=None, dirty=False)

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit=None, dirty=True)

        run("bzr add .")
        run('bzr commit -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", post=0, dev=0, commit="1", dirty=False)

        run("bzr tag v0.1.0")
        assert from_vcs() == Version("0.1.0", commit="1", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="1", dirty=False)
        assert run("dunamai from bazaar") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="1", dirty=True)

        run("bzr add .")
        run('bzr commit -m "Second"')
        assert from_vcs() == Version("0.1.0", post=1, dev=0, commit="2", dirty=False)
        assert from_any_vcs_unmocked() == Version("0.1.0", post=1, dev=0, commit="2", dirty=False)

        run("bzr tag unmatched")
        assert from_vcs() == Version("0.1.0", post=1, dev=0, commit="2", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)


def test__version__from_any_vcs(tmp_path):
    with chdir(tmp_path):
        with pytest.raises(RuntimeError):
            Version.from_any_vcs()


def test__check_version__pep440():
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


def test__check_version__semver():
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


def test__check_version__pvp():
    style = Style.Pvp

    check_version("1", style=style)
    check_version("0.1", style=style)
    check_version("0.0.1", style=style)
    check_version("0.0.0.1", style=style)
    check_version("0.1.0-alpha-1", style=style)

    with pytest.raises(ValueError):
        check_version("0.1.0-a.1", style=style)
