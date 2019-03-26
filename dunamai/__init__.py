__all__ = [
    "get_version",
    "Version",
]

import os
import pkg_resources
import re
import subprocess
from functools import total_ordering
from typing import Callable, Optional, Tuple


def _run_cmd(command: str) -> Tuple[int, str]:
    result = subprocess.run(
        "git describe --tags --long --dirty",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return (result.returncode, result.stdout.decode().strip())


@total_ordering
class Version:
    def __init__(
            self,
            base: str,
            *,
            epoch: int = None,
            pre: Tuple[str, int] = None,
            post: int = None,
            dev: int = None,
            commit: str = None,
            dirty: bool = None,
            source: str = None
        ) -> None:
        """
        :param base: Primary version part, such as 0.1.0.
        :param epoch: Epoch number.
        :param pre: Pair of prerelease type ("a", "b", "rc") and number.
        :param post: Postrelease number.
        :param dev: Development release number.
        :param commit: Commit hash/identifier.
        :param dirty: True if the working directory does not match the commit.
        :param source: Original reference string, such as from Git output.
        """
        self.base = base
        self.epoch = epoch
        if pre is None:
            self.pre_type = None
            self.pre_number = None
        else:
            self.pre_type, self.pre_number = pre
            if self.pre_type not in ["a", "b", "rc"]:
                raise ValueError("Unknown prerelease type: {}".format(self.pre_type))
        self.post = post
        self.dev = dev
        self.commit = commit
        self.dirty = dirty
        self.source = source

    def __str__(self) -> str:
        return self.serialize()

    def __repr__(self) -> str:
        return "Version(base={!r}, epoch={!r}, pre_type={!r}, pre_number={!r}, post={!r}, dev={!r}, commit={!r}, dirty={!r}, source={!r})" \
            .format(self.base, self.epoch, self.pre_type, self.pre_number, self.post, self.dev, self.commit, self.dirty, self.source)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Version):
            raise TypeError("Cannot compare Version with type {}".format(other.__class__.__qualname__))
        return pkg_resources.parse_version(self.serialize()) == pkg_resources.parse_version(other.serialize())

    def __lt__(self, other) -> bool:
        if not isinstance(other, Version):
            raise TypeError("Cannot compare Version with type {}".format(other.__class__.__qualname__))
        return pkg_resources.parse_version(self.serialize()) < pkg_resources.parse_version(other.serialize())

    def serialize(self, with_metadata: bool = False) -> str:
        """
        Create a string from the version info.

        :param with_metadata: Add the local version metadata if any exists.
        """
        out = ""

        if self.epoch is not None:
            out += "{}!".format(self.epoch)

        out += self.base

        if self.pre_type is not None and self.pre_number is not None:
            out += "{}{}".format(self.pre_type, self.pre_number)
        if self.post is not None:
            out += ".post{}".format(self.post)
        if self.dev is not None:
            out += ".dev{}".format(self.dev)

        if with_metadata:
            metadata_parts = [self.commit, "dirty" if self.dirty else None]
            metadata = ".".join(x for x in metadata_parts if x is not None)
            if metadata:
                out += "+{}".format(metadata)

        self._validate(out)
        return out

    def _validate(self, serialized: str) -> None:
        # PEP 440: [N!]N(.N)*[{a|b|rc}N][.postN][.devN][+<local version label>]
        if not re.match(r"^(\d!)?\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?(\+.+)?$", serialized):
            raise ValueError("Version '{}' does not conform to PEP 440".format(serialized))

    @classmethod
    def from_git_describe(
            cls,
            pattern: str = r"v(?P<base>\d+\.\d+\.\d+)((?P<pre_type>a|b|rc)(?P<pre_number>\d+))?",
            flag_dirty: bool = False
        ) -> "Version":
        r"""
        Create a version based on the output of `git describe`.

        :param pattern: Regular expression to be matched against the current
            Git tag. This should contain one capture group named `base`
            corresponding to the version part of the version part of the tag,
            and optionally another two groups named `pre_type` and `pre_number`
            corresponding to the type and number of prerelease. For example,
            with a tag like v0.1.0, the pattern would be `v(?P<base>\d+\.\d+\.\d+)`.
        :param flag_dirty: If true, add `dirty` to metadata if the working
            directory has uncommitted changes.
        """
        tag = None
        distance = None
        commit = None
        dirty = False
        pre = None
        post = None
        dev = None

        code, description = _run_cmd("git describe --tags --long --dirty")
        if code == 128:
            code, description = _run_cmd("git describe --always --dirty")
            if code == 128:
                return cls("0.0.0", post=0, dev=0, commit="initial")
            elif code == 0:
                commit, *dirty = description.split("-")
                return cls("0.0.0", post=0, dev=0, commit=commit, dirty=bool(dirty), source=description)
            else:
                raise RuntimeError("Git returned code {}".format(code))
        elif code == 0:
            tag, distance, commit, *dirty = description.split("-")
            distance = int(distance)
        else:
            raise RuntimeError("Git returned code {}".format(code))

        pattern_match = re.search(pattern, tag)
        if pattern_match is None:
            raise ValueError("Pattern '{}' did not match the tag '{}'".format(pattern, tag))
        try:
            base = pattern_match.group("base")
        except IndexError:
            raise ValueError("Pattern '{}' did not include required capture group 'base'".format(pattern))
        try:
            pre_type = pattern_match.group("pre_type")
            pre_number = pattern_match.group("pre_number")
            if pre_type is not None and pre_number is not None:
                pre = (pre_type, int(pre_number))
        except IndexError:
            pass

        if distance > 0:
            post = distance
            dev = 0

        dirty = bool(dirty) if flag_dirty else None

        return cls(base, pre=pre, post=post, dev=dev, commit=commit, dirty=dirty, source=description)


def get_version(
    name: str,
    first_choice: Callable[[], Optional[Version]] = None,
    third_choice: Callable[[], Optional[Version]] = None,
    fallback: Version = Version("0.0.0"),
) -> Version:
    """
    Check pkg_resources info or a fallback function to determine the version.
    This is intended as a convenient default for setting your `__version__` if
    you do not want to include a generated version statically during packaging.

    :param name: Installed package name.
    :param first_choice: Callback to determine a version before checking
        to see if the named package is installed.
    :param third_choice: Callback to determine a version if the installed
        package cannot be found by name.
    :param fallback: If no other matches found, use this version.
    """
    if first_choice:
        first_ver = first_choice()
        if first_ver:
            return first_ver

    try:
        return Version(pkg_resources.get_distribution(name).version)
    except pkg_resources.DistributionNotFound:
        pass

    if third_choice:
        third_ver = third_choice()
        if third_ver:
            return third_ver

    return fallback


__version__ = get_version(
    "dunamai",
    first_choice=lambda: Version.from_git_describe() if "DUNAMAI_DEV" in os.environ else None,
    third_choice=Version.from_git_describe,
).serialize()
