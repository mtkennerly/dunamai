import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional

import pytest

from dunamai import Version, Vcs, _run_cmd


def avoid_identical_ref_timestamps() -> None:
    time.sleep(1.2)


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


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires Git")
def test__version__from_git__with_annotated_tags(tmp_path) -> None:
    vcs = tmp_path / "dunamai-git-annotated"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_git)

    with chdir(vcs):
        run("git init")
        assert from_vcs() == Version("0.0.0", distance=0, commit=None, dirty=True)

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", distance=0, commit=None, dirty=True)

        run("git add .")
        run('git commit -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, commit="abc", dirty=False)

        # Additional one-off check not in other VCS integration tests:
        # when the only tag in the repository does not match the pattern.
        run("git tag other -m Annotated")
        with pytest.raises(ValueError):
            from_vcs()

        avoid_identical_ref_timestamps()
        run("git tag v0.1.0 -m Annotated")
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
        assert from_explicit_vcs(Vcs.Any) == Version("0.1.0", commit="abc", dirty=False)
        assert from_explicit_vcs(Vcs.Git) == Version("0.1.0", commit="abc", dirty=False)

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=True)

        run("git add .")
        run('git commit -m "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)
        assert from_any_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)

        run("git tag unmatched -m Annotated")
        assert from_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        avoid_identical_ref_timestamps()
        run("git tag v0.2.0 -m Annotated")
        avoid_identical_ref_timestamps()
        run("git tag v0.1.1 HEAD~1 -m Annotated")
        assert from_vcs() == Version("0.2.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.2.0", commit="abc", dirty=False)

        # Check handling with identical tag and branch names:
        run("git checkout -b v0.2.0")
        assert from_vcs() == Version("0.2.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.2.0", commit="abc", dirty=False)

        run("git checkout v0.1.0")
        assert from_vcs() == Version("0.1.1", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.1", commit="abc", dirty=False)

        # Additional one-off check not in other VCS integration tests:
        # tag with pre-release segment.
        run("git checkout master")
        (vcs / "foo.txt").write_text("third")
        run("git add .")
        run('git commit -m "Third"')
        run("git tag v0.2.1b3 -m Annotated")
        assert from_vcs() == Version("0.2.1", stage=("b", 3), commit="abc", dirty=False)


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires Git")
def test__version__from_git__with_lightweight_tags(tmp_path) -> None:
    vcs = tmp_path / "dunamai-git-lightweight"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_git)

    with chdir(vcs):
        run("git init")
        (vcs / "foo.txt").write_text("hi")
        run("git add .")
        run('git commit -m "Initial commit"')

        run("git tag v0.1.0")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="abc", dirty=False)
        assert run("dunamai from git") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        run("git add .")
        avoid_identical_ref_timestamps()
        run('git commit -m "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)
        assert from_any_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)

        (vcs / "foo.txt").write_text("again")
        run("git add .")
        avoid_identical_ref_timestamps()
        run('git commit -m "Third"')
        assert from_vcs() == Version("0.1.0", distance=2, commit="abc", dirty=False)
        assert from_any_vcs() == Version("0.1.0", distance=2, commit="abc", dirty=False)

        run("git tag v0.2.0")
        run("git tag v0.1.1 HEAD~1")
        assert from_vcs() == Version("0.2.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.2.0", commit="abc", dirty=False)

        run("git checkout v0.1.1")
        assert from_vcs() == Version("0.1.1", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.1", commit="abc", dirty=False)


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires Git")
def test__version__not_a_repository(tmp_path) -> None:
    vcs = tmp_path / "dunamai-not-a-repo"
    vcs.mkdir()
    run = make_run_callback(vcs)

    with chdir(vcs):
        assert run("dunamai from git", 1) == "This does not appear to be a Git project"


@pytest.mark.skipif(shutil.which("hg") is None, reason="Requires Mercurial")
def test__version__from_mercurial(tmp_path) -> None:
    vcs = tmp_path / "dunamai-hg"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_mercurial)

    with chdir(vcs):
        run("hg init")
        assert from_vcs() == Version("0.0.0", distance=0, commit=None, dirty=False)

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", distance=0, commit=None, dirty=True)

        run("hg add .")
        run('hg commit -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, commit="abc", dirty=False)

        run("hg tag v0.1.0")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="abc", dirty=False)
        assert run("dunamai from mercurial") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=True)

        run("hg add .")
        run('hg commit -m "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)
        assert from_any_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)

        run("hg tag unmatched")
        assert from_vcs() == Version("0.1.0", distance=2, commit="abc", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        run("hg tag v0.2.0")
        assert from_vcs() == Version("0.2.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.2.0", commit="abc", dirty=False)

        run('hg tag v0.1.1 -r "tag(v0.1.0)"')
        assert from_vcs() == Version("0.2.0", distance=1, commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.2.0", distance=1, commit="abc", dirty=False)

        run("hg checkout v0.1.0")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="abc", dirty=False)


@pytest.mark.skipif(shutil.which("darcs") is None, reason="Requires Darcs")
def test__version__from_darcs(tmp_path) -> None:
    vcs = tmp_path / "dunamai-darcs"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_darcs)

    with chdir(vcs):
        run("darcs init")
        assert from_vcs() == Version("0.0.0", distance=0, commit=None, dirty=False)

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", distance=0, commit=None, dirty=True)

        run("darcs add foo.txt")
        run('darcs record -am "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, commit="abc", dirty=False)

        run("darcs tag v0.1.0")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="abc", dirty=False)
        assert run("dunamai from darcs") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=True)

        run('darcs record -am "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)
        assert from_any_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)

        run("darcs tag unmatched")
        assert from_vcs() == Version("0.1.0", distance=2, commit="abc", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        run("darcs tag v0.2.0")
        assert from_vcs() == Version("0.2.0", commit="abc", dirty=False)

        run("darcs obliterate --all --last 3")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=False)


@pytest.mark.skipif(
    None in [shutil.which("svn"), shutil.which("svnadmin")], reason="Requires Subversion"
)
def test__version__from_subversion(tmp_path) -> None:
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
        assert from_vcs() == Version("0.0.0", distance=0, commit=None, dirty=False)

        run("svn mkdir trunk tags")
        (vcs / "trunk" / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", distance=0, commit=None, dirty=True)

        run("svn add --force .")
        run('svn commit -m "Initial commit"')  # commit 1
        run("svn update")
        assert from_vcs() == Version("0.0.0", distance=1, commit="1", dirty=False)

        run('svn copy {0}/trunk {0}/tags/v0.1.0 -m "Tag 1"'.format(vcs_srv_uri))  # commit 2
        run("svn update")
        assert from_vcs() == Version("0.1.0", commit="2", dirty=False)
        assert run("dunamai from subversion") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "trunk" / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="2", dirty=True)

        run('svn commit -m "Second"')  # commit 3
        run("svn update")
        assert from_vcs() == Version("0.1.0", distance=1, commit="3", dirty=False)
        assert from_any_vcs_unmocked() == Version("0.1.0", distance=1, commit="3", dirty=False)

        # Ensure we get the tag based on the highest commit, not necessarily
        # just the newest tag.
        run('svn copy {0}/trunk {0}/tags/v0.2.0 -m "Tag 2"'.format(vcs_srv_uri))  # commit 4
        run('svn copy {0}/trunk {0}/tags/v0.1.1 -r 1 -m "Tag 3"'.format(vcs_srv_uri))  # commit 5
        run("svn update")
        assert from_vcs() == Version("0.2.0", distance=1, commit="5", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.2.0", distance=1, commit="5", dirty=False)

        run('svn copy {0}/trunk {0}/tags/unmatched -m "Tag 4"'.format(vcs_srv_uri))  # commit 6
        run("svn update")
        assert from_vcs() == Version("0.2.0", distance=2, commit="6", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        run("svn update -r 2")
        assert from_vcs() == Version("0.1.0", commit="2", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="2", dirty=False)


@pytest.mark.skipif(shutil.which("bzr") is None, reason="Requires Bazaar")
def test__version__from_bazaar(tmp_path) -> None:
    vcs = tmp_path / "dunamai-bzr"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_bazaar, mock_commit=None)

    with chdir(vcs):
        run("bzr init")
        assert from_vcs() == Version("0.0.0", distance=0, commit=None, dirty=False)

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", distance=0, commit=None, dirty=True)

        run("bzr add .")
        run('bzr commit -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, commit="1", dirty=False)

        run("bzr tag v0.1.0")
        assert from_vcs() == Version("0.1.0", commit="1", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="1", dirty=False)
        assert run("dunamai from bazaar") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="1", dirty=True)

        run("bzr add .")
        run('bzr commit -m "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, commit="2", dirty=False)
        assert from_any_vcs_unmocked() == Version("0.1.0", distance=1, commit="2", dirty=False)

        run("bzr tag unmatched")
        assert from_vcs() == Version("0.1.0", distance=1, commit="2", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        run("bzr tag v0.2.0")
        run("bzr tag v0.1.1 -r v0.1.0")
        assert from_vcs() == Version("0.2.0", commit="2", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.2.0", commit="2", dirty=False)

        run("bzr checkout . old -r v0.1.0")

    with chdir(vcs / "old"):
        assert from_vcs() == Version("0.1.1", commit="1", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.1", commit="1", dirty=False)


@pytest.mark.skipif(shutil.which("fossil") is None, reason="Requires Fossil")
def test__version__from_fossil(tmp_path) -> None:
    vcs = tmp_path / "dunamai-fossil"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_fossil)

    with chdir(vcs):
        run("fossil init repo")
        run("fossil open repo")
        assert from_vcs() == Version("0.0.0", distance=0, commit="abc", dirty=False)

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", distance=0, commit="abc", dirty=True)

        run("fossil add .")
        run('fossil commit -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, commit="abc", dirty=False)

        run("fossil tag add v0.1.0 trunk")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="abc", dirty=False)
        assert run("dunamai from fossil") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="abc", dirty=True)

        run("fossil add .")
        run('fossil commit -m "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)
        assert from_any_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)

        run("fossil tag add unmatched trunk")
        assert from_vcs() == Version("0.1.0", distance=1, commit="abc", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        (vcs / "foo.txt").write_text("third")
        run("fossil add .")
        run("fossil commit --tag v0.2.0 -m 'Third'")
        assert from_vcs() == Version("0.2.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.2.0", commit="abc", dirty=False)

        run("fossil tag add v0.1.1 v0.1.0")
        assert from_vcs() == Version("0.2.0", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.2.0", commit="abc", dirty=False)

        run("fossil checkout v0.1.0")
        assert from_vcs() == Version("0.1.1", commit="abc", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.1", commit="abc", dirty=False)
