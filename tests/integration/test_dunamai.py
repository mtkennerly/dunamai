import datetime as dt
import os
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, List, Optional

import pytest

from dunamai import Version, Vcs, Concern, _get_git_version, _run_cmd


def avoid_identical_ref_timestamps() -> None:
    time.sleep(1.2)


def lacks_git_version(version: List[int]) -> bool:
    if shutil.which("git") is None:
        return True
    return _get_git_version() < version


REPO = Path(__file__).parent.parent.parent


@contextmanager
def chdir(where: Path) -> Iterator[None]:
    start = Path.cwd()
    os.chdir(str(where))
    try:
        yield
    finally:
        os.chdir(str(start))


def is_git_legacy() -> bool:
    version = _get_git_version()
    return version < [2, 7]


def set_missing_env(key: str, value: str, alts: Optional[List[str]] = None) -> None:
    if alts is None:
        alts = []

    for k in [key, *alts]:
        if os.environ.get(k) is not None:
            return

    os.environ[key] = value


def make_run_callback(where: Path) -> Callable:
    def inner(command, expected_code: int = 0, env: Optional[dict] = None):
        _, out = _run_cmd(command, where=where, codes=[expected_code], env=env)
        return out

    return inner


def make_from_callback(
    function: Callable, clear: bool = True, chronological: bool = True
) -> Callable:
    def inner(*args, fresh: bool = False, **kwargs):
        version = function(*args, **kwargs)
        if fresh:
            assert version.commit is None
            assert version.timestamp is None
        else:
            assert isinstance(version.commit, str)
            assert len(version.commit) > 0

            if chronological:
                assert isinstance(version.timestamp, dt.datetime)
                now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
                delta = dt.timedelta(minutes=1)
                assert now - delta <= version.timestamp <= now + delta
        if clear:
            version.commit = None
        version.timestamp = None
        return version

    return inner


from_any_vcs = make_from_callback(Version.from_any_vcs)
from_any_vcs_unmocked = make_from_callback(Version.from_any_vcs, clear=False)
from_explicit_vcs = make_from_callback(Version.from_vcs)


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires Git")
def test__version__from_git__with_annotated_tags(tmp_path) -> None:
    vcs = tmp_path / "dunamai-git-annotated"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_git)
    b = "master"
    legacy = is_git_legacy()

    with chdir(vcs):
        run("git init")
        try:
            # Compatibility for newer Git versions:
            run("git branch -m master")
        except Exception:
            pass
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=True, branch=b)
        assert from_vcs(fresh=True).vcs == Vcs.Git

        # Additional one-off check not in other VCS integration tests:
        # strict mode requires there to be a tag
        with pytest.raises(RuntimeError):
            from_vcs(strict=True)

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=True, branch=b)
        assert from_vcs(fresh=True).concerns == set()

        run("git add .")
        run('git commit --no-gpg-sign -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, dirty=False, branch=b)

        # Detect dirty if untracked files
        (vcs / "bar.txt").write_text("bye")
        assert from_vcs() == Version("0.0.0", distance=1, dirty=True, branch=b)

        # Once the untracked file is removed we are no longer dirty
        (vcs / "bar.txt").unlink()
        assert from_vcs() == Version("0.0.0", distance=1, dirty=False, branch=b)

        # Additional one-off check not in other VCS integration tests:
        # when the only tag in the repository does not match the pattern.
        run("git tag other -m Annotated")
        with pytest.raises(ValueError):
            from_vcs()

        avoid_identical_ref_timestamps()
        run("git tag v0.1.0 -m Annotated")
        assert from_vcs() == Version("0.1.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.1.0", dirty=False, branch=b)
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
        assert from_explicit_vcs(Vcs.Any) == Version("0.1.0", dirty=False, branch=b)
        assert from_explicit_vcs(Vcs.Git) == Version("0.1.0", dirty=False, branch=b)
        assert run("dunamai from any --bump") == "0.1.0"
        assert run('dunamai from git --format "{commit}"') != run(
            'dunamai from git --format "{commit}" --full-commit'
        )
        assert run('dunamai from any --format "{commit}"') != run(
            'dunamai from any --format "{commit}" --full-commit'
        )

        if not legacy:
            # Verify tags with '/' work
            run("git tag test/v0.1.0")
            assert run(r'dunamai from any --pattern "^test/v(?P<base>\d\.\d\.\d)"') == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", dirty=True, branch=b)

        run("git add .")
        run('git commit --no-gpg-sign -m "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)
        assert from_any_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)

        run("git tag unmatched -m Annotated")
        assert from_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        # check that we find the expected tag that has the most recent tag creation time
        if legacy:
            run("git tag -d unmatched")
            run("git tag v0.2.0 -m Annotated")
        if not legacy:
            avoid_identical_ref_timestamps()
            run("git tag v0.2.0b1 -m Annotated")
            avoid_identical_ref_timestamps()
            run("git tag v0.2.0 -m Annotated")
            avoid_identical_ref_timestamps()
            run("git tag v0.1.1 HEAD~1 -m Annotated")
        assert from_vcs() == Version("0.2.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.2.0", dirty=False, branch=b)

        # Check handling with identical tag and branch names:
        run("git checkout -b v0.2.0")
        assert from_vcs() == Version("0.2.0", dirty=False, branch="heads/v0.2.0")
        assert from_vcs(latest_tag=True) == Version("0.2.0", dirty=False, branch="heads/v0.2.0")

        if not legacy:
            run("git checkout v0.1.0")
            assert from_vcs() == Version("0.1.1", dirty=False)
            assert from_vcs(latest_tag=True) == Version("0.1.1", dirty=False)

        # Additional one-off check not in other VCS integration tests:
        run("git checkout master")
        (vcs / "foo.txt").write_text("third")
        run("git add .")
        run('git commit --no-gpg-sign -m "Third"')
        # bumping:
        commit = run('dunamai from any --format "{commit}"')
        assert run("dunamai from any --bump") == "0.2.1.dev1+{}".format(commit)
        if not legacy:
            # tag with pre-release segment.
            run("git tag v0.2.1b3 -m Annotated")
            assert from_vcs() == Version("0.2.1", stage=("b", 3), dirty=False, branch=b)

        if not legacy:
            # Additional one-off check: tag containing comma.
            (vcs / "foo.txt").write_text("fourth")
            run("git add .")
            run('git commit --no-gpg-sign -m "Fourth"')
            run("git tag v0.3.0+a,b -m Annotated")
            assert from_vcs() == Version("0.3.0", dirty=False, tagged_metadata="a,b", branch=b)

    if not legacy:
        assert from_vcs(path=vcs) == Version("0.3.0", dirty=False, tagged_metadata="a,b", branch=b)


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires Git")
def test__version__from_git__with_lightweight_tags(tmp_path) -> None:
    vcs = tmp_path / "dunamai-git-lightweight"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_git)
    b = "master"
    legacy = is_git_legacy()

    with chdir(vcs):
        run("git init")
        (vcs / "foo.txt").write_text("hi")
        run("git add .")
        run('git commit --no-gpg-sign -m "Initial commit"')

        run("git tag v0.1.0")
        assert from_vcs() == Version("0.1.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.1.0", dirty=False, branch=b)
        assert run("dunamai from git") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        run("git add .")
        avoid_identical_ref_timestamps()
        run('git commit --no-gpg-sign -m "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)
        assert from_any_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)

        (vcs / "foo.txt").write_text("again")
        run("git add .")
        avoid_identical_ref_timestamps()
        run('git commit --no-gpg-sign -m "Third"')
        assert from_vcs() == Version("0.1.0", distance=2, dirty=False, branch=b)
        assert from_any_vcs() == Version("0.1.0", distance=2, dirty=False, branch=b)

        run("git tag v0.2.0")
        run("git tag v0.1.1 HEAD~1")
        assert from_vcs() == Version("0.2.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.2.0", dirty=False, branch=b)

        if not legacy:
            run("git checkout v0.1.1")
            assert from_vcs() == Version("0.1.1", dirty=False)
            assert from_vcs(latest_tag=True) == Version("0.1.1", dirty=False)


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires Git")
def test__version__from_git__with_mixed_tags(tmp_path) -> None:
    vcs = tmp_path / "dunamai-git-mixed"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_git)
    b = "master"

    with chdir(vcs):
        run("git init")
        (vcs / "foo.txt").write_text("hi")
        run("git add .")
        run('git commit --no-gpg-sign -m "Initial commit"')

        run("git tag v0.1.0")
        (vcs / "foo.txt").write_text("hi 2")
        run("git add .")
        avoid_identical_ref_timestamps()
        run('git commit --no-gpg-sign -m "Second"')

        run('git tag v0.2.0 -m "Annotated"')
        assert from_vcs() == Version("0.2.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.2.0", dirty=False, branch=b)

        (vcs / "foo.txt").write_text("hi 3")
        run("git add .")
        avoid_identical_ref_timestamps()
        run('git commit --no-gpg-sign -m "Third"')

        run("git tag v0.3.0")
        assert from_vcs() == Version("0.3.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.3.0", dirty=False, branch=b)


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires Git")
def test__version__from_git__with_nonchronological_commits(tmp_path) -> None:
    vcs = tmp_path / "dunamai-git-nonchronological"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_git, chronological=False)
    b = "master"
    legacy = is_git_legacy()

    with chdir(vcs):
        run("git init")
        (vcs / "foo.txt").write_text("hi")
        run("git add .")
        run(
            'git commit --no-gpg-sign -m "Initial commit"',
            env={
                "GIT_COMMITTER_DATE": "2000-01-02T01:00:00",
                "GIT_AUTHOR_DATE": "2000-01-02T01:00:00",
                **os.environ,
            },
        )

        run("git tag v0.1.0")
        (vcs / "foo.txt").write_text("hi 2")
        run("git add .")
        avoid_identical_ref_timestamps()
        run(
            'git commit --no-gpg-sign -m "Second"',
            env={
                "GIT_COMMITTER_DATE": "2000-01-01T01:00:00",
                "GIT_AUTHOR_DATE": "2000-01-01T01:00:00",
                **os.environ,
            },
        )

        run("git tag v0.2.0")
        if legacy:
            assert from_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)
        else:
            assert from_vcs() == Version("0.2.0", dirty=False, branch=b)


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires Git")
@pytest.mark.skipif(is_git_legacy(), reason="Requires non-legacy Git")
def test__version__from_git__gitflow(tmp_path) -> None:
    vcs = tmp_path / "dunamai-git-gitflow"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_git)
    b = "master"
    b2 = "develop"

    with chdir(vcs):
        run("git init")
        (vcs / "foo.txt").write_text("hi")
        run("git add .")
        run("git commit --no-gpg-sign -m Initial")
        run("git tag v0.1.0 -m Release")

        run("git checkout -b develop")
        (vcs / "foo.txt").write_text("second")
        run("git add .")
        run("git commit --no-gpg-sign -m Second")

        run("git checkout -b release/v0.2.0")
        (vcs / "foo.txt").write_text("bugfix")
        run("git add .")
        run("git commit --no-gpg-sign -m Bugfix")

        run("git checkout develop")
        run("git merge --no-gpg-sign --no-ff release/v0.2.0")

        run("git checkout master")
        run("git merge --no-gpg-sign --no-ff release/v0.2.0")

        run("git tag v0.2.0 -m Release")
        assert from_vcs() == Version("0.2.0", dirty=False, branch=b)

        run("git checkout develop")
        assert from_vcs() == Version("0.1.0", distance=3, dirty=False, branch=b2)
        assert run('dunamai from any --format "{base}+{distance}"') == "0.1.0+3"
        assert from_vcs(tag_branch="master") == Version("0.2.0", distance=1, dirty=False, branch=b2)
        assert run('dunamai from any --tag-branch master --format "{base}+{distance}"') == "0.2.0+1"
        assert run('dunamai from git --tag-branch master --format "{base}+{distance}"') == "0.2.0+1"

        (vcs / "foo.txt").write_text("feature")
        run("git add .")
        run("git commit --no-gpg-sign -m Feature")
        assert from_vcs() == Version("0.1.0", distance=4, dirty=False, branch=b2)
        assert from_vcs(tag_branch="master") == Version("0.2.0", distance=2, dirty=False, branch=b2)

        run("git checkout master")
        assert from_vcs() == Version("0.2.0", dirty=False, branch=b)
        assert from_vcs(tag_branch="master") == Version("0.2.0", dirty=False, branch=b)
        assert from_vcs(tag_branch="develop") == Version("0.1.0", distance=3, dirty=False, branch=b)


def test__version__from_git__archival_untagged() -> None:
    with chdir(REPO / "tests" / "archival" / "git-untagged"):
        detected = Version.from_git()
        assert detected == Version(
            "0.0.0",
            branch="master",
            commit="8fe614d",
            timestamp=dt.datetime(2022, 11, 6, 23, 7, 50, tzinfo=dt.timezone.utc),
        )
        assert detected._matched_tag is None
        assert detected._newer_unmatched_tags is None

        assert Version.from_any_vcs() == detected

        assert (
            Version.from_git(full_commit=True).commit == "8fe614dbf9e767e70442ab8f56e99bd08d7e782d"
        )

        with pytest.raises(RuntimeError):
            Version.from_git(strict=True)


def test__version__from_git__archival_tagged() -> None:
    with chdir(REPO / "tests" / "archival" / "git-tagged"):
        detected = Version.from_git()
        assert detected == Version(
            "0.1.0",
            branch="master",
            dirty=False,
            distance=0,
            commit="8fe614d",
            timestamp=dt.datetime(2022, 11, 6, 23, 7, 50, tzinfo=dt.timezone.utc),
        )
        assert detected._matched_tag == "v0.1.0"
        assert detected._newer_unmatched_tags == []


def test__version__from_git__archival_tagged_post() -> None:
    with chdir(REPO / "tests" / "archival" / "git-tagged-post"):
        detected = Version.from_git()
        assert detected == Version(
            "0.1.0",
            branch="master",
            dirty=False,
            distance=1,
            commit="1b57ff7",
            timestamp=dt.datetime(2022, 11, 6, 23, 16, 59, tzinfo=dt.timezone.utc),
        )
        assert detected._matched_tag == "v0.1.0"
        assert detected._newer_unmatched_tags == []


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires Git")
def test__version__from_git__shallow(tmp_path) -> None:
    vcs = tmp_path / "dunamai-git-shallow"
    vcs.mkdir()
    run = make_run_callback(vcs)

    with chdir(vcs):
        run("git clone --depth 1 https://github.com/mtkennerly/dunamai.git .")
        assert Version.from_git().concerns == {Concern.ShallowRepository}

        with pytest.raises(RuntimeError):
            Version.from_git(strict=True)


@pytest.mark.skipif(lacks_git_version([2, 27]), reason="Requires Git 2.27+")
def test__version__from_git__exclude_decoration(tmp_path) -> None:
    vcs = tmp_path / "dunamai-git-exclude-decoration"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_git)
    b = "master"

    with chdir(vcs):
        run("git init")
        (vcs / "foo.txt").write_text("hi")
        run("git add .")
        run("git commit --no-gpg-sign -m Initial")
        run("git tag v0.1.0 -m Release")
        run("git config log.excludeDecoration refs/tags/")

        assert from_vcs() == Version("0.1.0", dirty=False, branch=b)


# Older versions of Git fail with code 128:
# "fatal: missing object 0000000000000000000000000000000000000000 for refs/tags/bad.txt"
@pytest.mark.skipif(lacks_git_version([2, 7]), reason="Requires Git 2.7+")
def test__version__from_git__broken_ref(tmp_path) -> None:
    vcs = tmp_path / "dunamai-git-broken-ref"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_git)
    b = "master"

    with chdir(vcs):
        run("git init")
        (vcs / "foo.txt").write_text("hi")
        run("git add .")
        run("git commit --no-gpg-sign -m Initial")
        run("git tag v0.1.0 -m Release")
        (vcs / ".git/refs/tags/bad.txt").touch()

        assert from_vcs() == Version("0.1.0", dirty=False, branch=b)


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
    b = "default"

    with chdir(vcs):
        run("hg init")
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=False, branch=b)
        assert from_vcs(fresh=True).vcs == Vcs.Mercurial

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=True, branch=b)

        run("hg add .")
        run('hg commit -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, dirty=False, branch=b)
        assert run('dunamai from mercurial --format "{commit}"') != run(
            'dunamai from mercurial --format "{commit}" --full-commit'
        )
        assert run('dunamai from any --format "{commit}"') != run(
            'dunamai from any --format "{commit}" --full-commit'
        )

        run("hg tag v0.1.0")
        assert from_vcs() == Version("0.1.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.1.0", dirty=False, branch=b)
        assert run("dunamai from mercurial") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", dirty=True, branch=b)

        run("hg add .")
        run('hg commit -m "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)
        assert from_any_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)

        run("hg tag unmatched")
        assert from_vcs() == Version("0.1.0", distance=2, dirty=False, branch=b)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        run("hg tag v0.2.0")
        assert from_vcs() == Version("0.2.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.2.0", dirty=False, branch=b)

        run('hg tag v0.1.1 -r "tag(v0.1.0)"')
        assert from_vcs() == Version("0.2.0", distance=1, dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.2.0", distance=1, dirty=False, branch=b)

        run("hg checkout v0.1.0")
        assert from_vcs() == Version("0.1.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.1.0", dirty=False, branch=b)

    assert from_vcs(path=vcs) == Version("0.1.0", dirty=False, branch=b)


def test__version__from_mercurial__archival_untagged() -> None:
    with chdir(REPO / "tests" / "archival" / "hg-untagged"):
        detected = Version.from_mercurial()
        assert detected == Version(
            "0.0.0",
            branch="default",
            commit="25e474af1332ed4fff9351c70ef8f36352c013f2",
        )
        assert detected._matched_tag is None
        assert detected._newer_unmatched_tags is None

        assert Version.from_any_vcs() == detected

        with pytest.raises(RuntimeError):
            Version.from_mercurial(strict=True)


def test__version__from_mercurial__archival_tagged() -> None:
    with chdir(REPO / "tests" / "archival" / "hg-tagged"):
        detected = Version.from_mercurial()
        assert detected == Version(
            "0.1.1",
            branch="default",
            commit="cf36273384e558411364a3a973aaa0cc08e48aea",
        )
        assert detected._matched_tag == "v0.1.1"
        assert detected._newer_unmatched_tags == ["foo bar"]


@pytest.mark.skipif(shutil.which("darcs") is None, reason="Requires Darcs")
def test__version__from_darcs(tmp_path) -> None:
    vcs = tmp_path / "dunamai-darcs"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_darcs)

    with chdir(vcs):
        run("darcs init")
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=False)
        assert from_vcs(fresh=True).vcs == Vcs.Darcs

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=True)

        run("darcs add foo.txt")
        run('darcs record -am "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, dirty=False)

        run("darcs tag v0.1.0")
        assert from_vcs() == Version("0.1.0", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.1.0", dirty=False)
        assert run("dunamai from darcs") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", dirty=True)

        run('darcs record -am "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, dirty=False)
        assert from_any_vcs() == Version("0.1.0", distance=1, dirty=False)

        run("darcs tag unmatched")
        assert from_vcs() == Version("0.1.0", distance=2, dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        run("darcs tag v0.2.0")
        assert from_vcs() == Version("0.2.0", dirty=False)

        run("darcs obliterate --all --last 3")
        assert from_vcs() == Version("0.1.0", dirty=False)

    assert from_vcs(path=vcs) == Version("0.1.0", dirty=False)


@pytest.mark.skipif(
    None in [shutil.which("svn"), shutil.which("svnadmin")], reason="Requires Subversion"
)
def test__version__from_subversion(tmp_path) -> None:
    vcs = tmp_path / "dunamai-svn"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_subversion, clear=False)

    vcs_srv = tmp_path / "dunamai-svn-srv"
    vcs_srv.mkdir()
    run_srv = make_run_callback(vcs_srv)
    vcs_srv_uri = vcs_srv.as_uri()

    with chdir(vcs_srv):
        run_srv("svnadmin create .")

    with chdir(vcs):
        run('svn checkout "{}" .'.format(vcs_srv_uri))
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=False)
        assert from_vcs(fresh=True).vcs == Vcs.Subversion

        run("svn mkdir trunk tags")

        # No tags yet, so version should be 0.0.0.
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=True)

        run("svn add --force .")
        run('svn commit -m "Initial commit"')  # commit 1
        run("svn update")

        # A single commit, but still no tags. Version should be 0.0.0.
        assert from_vcs() == Version("0.0.0", distance=1, commit="1", dirty=False)

        with chdir(vcs / "trunk"):
            # ^-- Make sure things work when we're in trunk, too.
            Path("foo.txt").write_text("hi")
            run("svn add --force .")
            run('svn commit -m "Initial foo.txt commit"')  # commit 2
            run("svn update")

            # Two commits, but still no tag. Version should still be 0.0.0.
            assert from_vcs() == Version("0.0.0", distance=2, commit="2", dirty=False)

            run(
                'svn copy {0}/trunk {0}/tags/v0.1.0 -m "Tag 1"'.format(vcs_srv_uri)
            )  # commit 3 and first tag!
            run("svn update")

            # 3 commits, one tag (v.0.1.0), version should be 0.1.0.
            assert from_vcs() == Version("0.1.0", commit="3", dirty=False)
            assert run("dunamai from subversion") == "0.1.0"
            assert run("dunamai from any") == "0.1.0"

        # Dirty the working directory. Make sure we identify it as such.
        (vcs / "trunk" / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="3", dirty=True)

        # Fourth commit, still just one tag. Version should be 0.1.0, and dirty flag
        # should be reset.
        run('svn commit -m "Fourth"')  # commit 4
        run("svn update")
        assert from_vcs() == Version("0.1.0", distance=1, commit="4", dirty=False)
        assert from_any_vcs_unmocked() == Version("0.1.0", distance=1, commit="4", dirty=False)

        # Ensure we get the tag based on the highest commit, not necessarily
        # just the newest tag.
        run('svn copy {0}/trunk {0}/tags/v0.2.0 -m "Tag 2"'.format(vcs_srv_uri))  # commit 5
        run('svn copy {0}/trunk {0}/tags/v0.1.1 -r 1 -m "Tag 3"'.format(vcs_srv_uri))  # commit 6
        run("svn update")
        assert from_vcs() == Version("0.2.0", distance=1, commit="6", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.2.0", distance=1, commit="6", dirty=False)

        run('svn copy {0}/trunk {0}/tags/unmatched -m "Tag 4"'.format(vcs_srv_uri))  # commit 7
        run("svn update")
        assert from_vcs() == Version("0.2.0", distance=2, commit="7", dirty=False)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        # Checkout an earlier commit. Commit 2 occurred before the first tag
        # (v0.1.0, commit #3), so version should be 0.0.0.
        run("svn update -r 2")
        assert from_vcs() == Version("0.0.0", distance=2, commit="2", dirty=False)
        assert from_vcs(latest_tag=True) == Version("0.0.0", distance=2, commit="2", dirty=False)

        with chdir(vcs / "trunk"):
            # Do this in trunk, to make sure things still work there.
            # Checkout an earlier commit. Commit 3 was first tag (v0.1.0, commit
            # #3), so version should be 0.1.0.
            run("svn update -r 3")
            assert from_vcs() == Version("0.1.0", distance=0, commit="3", dirty=False)
            assert from_vcs(latest_tag=True) == Version(
                "0.1.0", distance=0, commit="3", dirty=False
            )

    assert from_vcs(path=vcs) == Version("0.1.0", distance=0, commit="3", dirty=False)


@pytest.mark.skipif(shutil.which("bzr") is None, reason="Requires Bazaar")
def test__version__from_bazaar(tmp_path) -> None:
    vcs = tmp_path / "dunamai-bzr"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_bazaar, clear=False)
    b = "dunamai-bzr"

    with chdir(vcs):
        run("bzr init")
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=False)
        assert from_vcs(fresh=True).vcs == Vcs.Bazaar

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=True)

        run("bzr add .")
        run('bzr commit -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, commit="1", dirty=False, branch=b)

        run("bzr tag v0.1.0")
        assert from_vcs() == Version("0.1.0", commit="1", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.1.0", commit="1", dirty=False, branch=b)
        assert run("dunamai from bazaar") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", commit="1", dirty=True, branch=b)

        run("bzr add .")
        run('bzr commit -m "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, commit="2", dirty=False, branch=b)
        assert from_any_vcs_unmocked() == Version(
            "0.1.0", distance=1, commit="2", dirty=False, branch=b
        )

        run("bzr tag unmatched")
        assert from_vcs() == Version("0.1.0", distance=1, commit="2", dirty=False, branch=b)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        run("bzr tag v0.2.0")
        run("bzr tag v0.1.1 -r v0.1.0")
        assert from_vcs() == Version("0.2.0", commit="2", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.2.0", commit="2", dirty=False, branch=b)

        run("bzr checkout . old -r v0.1.0")

    with chdir(vcs / "old"):
        assert from_vcs() == Version("0.1.1", commit="1", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.1.1", commit="1", dirty=False, branch=b)

    with chdir(vcs):
        shutil.rmtree("old")
        run("bzr nick renamed")
        assert from_vcs() == Version("0.2.0", commit="2", dirty=False, branch=b)
        (vcs / "foo.txt").write_text("branched")
        run("bzr add .")
        run('bzr commit -m "branched"')
        assert from_vcs() == Version("0.2.0", distance=1, commit="3", dirty=False, branch="renamed")
        run("bzr tag v0.2.1")
        assert from_vcs() == Version("0.2.1", commit="3", dirty=False, branch="renamed")

    assert from_vcs(path=vcs) == Version("0.2.1", commit="3", dirty=False, branch="renamed")


@pytest.mark.skipif(shutil.which("fossil") is None, reason="Requires Fossil")
def test__version__from_fossil(tmp_path) -> None:
    vcs = tmp_path / "dunamai-fossil"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_fossil)
    b = "trunk"

    if sys.platform != "win32":
        set_missing_env("FOSSIL_HOME", str(REPO / "tests"), ["HOME", "XDG_CONFIG_HOME"])
        set_missing_env("USER", "dunamai")

    with chdir(vcs):
        run("fossil init repo")
        run("fossil open repo --force")
        assert from_vcs() == Version("0.0.0", distance=0, dirty=False, branch=b)
        assert from_vcs().vcs == Vcs.Fossil

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs() == Version("0.0.0", distance=0, dirty=True, branch=b)

        run("fossil add .")
        run('fossil commit -m "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, dirty=False, branch=b)

        run("fossil tag add v0.1.0 trunk")
        assert from_vcs() == Version("0.1.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.1.0", dirty=False, branch=b)
        assert run("dunamai from fossil") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", dirty=True, branch=b)

        run("fossil add .")
        run('fossil commit -m "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)
        assert from_any_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)

        run("fossil tag add unmatched trunk")
        assert from_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

        (vcs / "foo.txt").write_text("third")
        run("fossil add .")
        run("fossil commit --tag v0.2.0 -m 'Third'")
        assert from_vcs() == Version("0.2.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.2.0", dirty=False, branch=b)

        run("fossil tag add v0.1.1 v0.1.0")
        assert from_vcs() == Version("0.2.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.2.0", dirty=False, branch=b)

        run("fossil checkout v0.1.0")
        assert from_vcs() == Version("0.1.1", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.1.1", dirty=False, branch=b)

    assert from_vcs(path=vcs) == Version("0.1.1", dirty=False, branch=b)


@pytest.mark.skipif(shutil.which("pijul") is None, reason="Requires Pijul")
def test__version__from_pijul(tmp_path) -> None:
    vcs = tmp_path / "dunamai-pijul"
    vcs.mkdir()
    run = make_run_callback(vcs)
    from_vcs = make_from_callback(Version.from_pijul)
    b = "main"

    with chdir(vcs):
        run("pijul init")
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=False, branch=b)
        assert from_vcs(fresh=True).vcs == Vcs.Pijul

        (vcs / "foo.txt").write_text("hi")
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=False, branch=b)

        run("pijul add foo.txt")
        assert from_vcs(fresh=True) == Version("0.0.0", distance=0, dirty=True, branch=b)
        run('pijul record . -am "Initial commit"')
        assert from_vcs() == Version("0.0.0", distance=1, dirty=False, branch=b)

        run("pijul tag create -m v0.1.0")
        assert from_vcs() == Version("0.1.0", dirty=False, branch=b)
        assert from_vcs(latest_tag=True) == Version("0.1.0", dirty=False, branch=b)
        assert run("dunamai from pijul") == "0.1.0"
        assert run("dunamai from any") == "0.1.0"

        (vcs / "foo.txt").write_text("bye")
        assert from_vcs() == Version("0.1.0", dirty=True, branch=b)

        run('pijul record . -am "Second"')
        assert from_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)
        assert from_any_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)

        run("pijul tag create -m unmatched")
        assert from_vcs() == Version("0.1.0", distance=1, dirty=False, branch=b)
        with pytest.raises(ValueError):
            from_vcs(latest_tag=True)

    assert from_vcs(path=vcs) == Version("0.1.0", distance=1, dirty=False, branch=b)
