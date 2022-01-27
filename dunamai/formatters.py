from typing import Sequence, Union
from dunamai import Version


def format_pieces_as_pep440(
    base: str,
    stage: str = None,
    revision: int = None,
    post: int = None,
    dev: int = None,
    epoch: int = None,
    metadata: Sequence[Union[str, int]] = None,
) -> str:
    """
    Serialize a version based on PEP 440.
    Use this helper function to format the individual pieces into a format string.

    :param base: Release segment, such as 0.1.0.
    :param stage: Pre-release stage ("a", "b", or "rc").
    :param revision: Pre-release revision (e.g., 1 as in "rc1").
        This is ignored when `stage` is None.
    :param post: Post-release number.
    :param dev: Developmental release number.
    :param epoch: Epoch number.
    :param metadata: Any local version label segments.
    :return: Serialized version.
    """
    out = []  # type: list

    if epoch is not None:
        out.extend([epoch, "!"])

    out.append(base)

    if stage is not None:
        alternative_stages = {"alpha": "a", "beta": "b", "c": "rc", "pre": "rc", "preview": "rc"}
        out.append(alternative_stages.get(stage.lower(), stage.lower()))
        if revision is None:
            # PEP 440 does not allow omitting the revision, so assume 0.
            out.append(0)
        else:
            out.append(revision)

    if post is not None:
        out.extend([".post", post])

    if dev is not None:
        out.extend([".dev", dev])

    if metadata is not None and len(metadata) > 0:
        out.extend(["+", ".".join(map(str, metadata))])

    serialized = "".join(map(str, out))
    return serialized


def pep440(version: Version) -> str:
    """
    Serialize a version based on PEP 440. (e.g. 0.1.0a8.post3+gf001c3f.dirty.linux).
    Use this with `Version.serialize_with_formatter()` if you want more control
    over how the version is mapped.

    :param version: The version.
    :return: Serialized version.
    """
    metadata = version.tagged_metadata
    if version.commit:
        if version.tagged_metadata:
            metadata = [version.commit, version.tagged_metadata]
        else:
            metadata = [version.commit]
    return format_pieces_as_pep440(
        version.base,
        stage=version.stage,
        revision=version.revision,
        post=version.distance,
        epoch=version.epoch,
        metadata=metadata,
    )


def pep440_meta(version: Version) -> str:
    """
    Serialize a version based on PEP 440, with the distance and commit in the
    metadata. (e.g. 0.1.0a8+3.f001c3f.dirty.linux).
    Use this with `Version.serialize_with_formatter()` if you want more control
    over how the version is mapped.

    :param version: The version.
    :return: Serialized version.
    """
    metadata = []
    if version.distance:
        metadata.extend([f"{version.distance}", f"{version.commit}"])
    if version.dirty:
        metadata.append("dirty")
    if version.tagged_metadata:
        filter_list = [version.distance, version.commit, "dirty"]
        metadata.extend(
            [
                m
                for m in [e.strip() for e in version.tagged_metadata.split(".")]
                if m not in filter_list
            ]
        )
    return format_pieces_as_pep440(
        version.base,
        stage=version.stage,
        revision=version.revision,
        epoch=version.epoch,
        metadata=metadata,
    )


def pep440_meta_id(version: Version) -> str:
    """
    Serialize a version based on PEP 440, with the distance and commit in the
    metadata. The distance and commit are preceded by an identifier. (e.g. 0.1.0a8+d3.gf001c3f.dirty.linux).
    Use this with `Version.serialize_with_formatter()` if you want more control
    over how the version is mapped.

    :param version: The version.
    :return: Serialized version.
    """
    metadata = []
    if version.distance:
        metadata.extend([f"d{version.distance}", f"g{version.commit}"])
    if version.dirty:
        metadata.append("dirty")
    if version.tagged_metadata:
        filter_list = [
            version.distance,
            f"d{version.distance}",
            version.commit,
            f"g{version.commit}",
            "dirty",
        ]
        metadata.extend(
            [
                m
                for m in [e.strip() for e in version.tagged_metadata.split(".")]
                if m not in filter_list
            ]
        )
    return format_pieces_as_pep440(
        version.base,
        stage=version.stage,
        revision=version.revision,
        epoch=version.epoch,
        metadata=metadata,
    )
