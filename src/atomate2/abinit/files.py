"""Functions for manipulating Abinit files."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, Union

from abipy.flowtk.utils import abi_extensions
from monty.serialization import loadfn

from atomate2.abinit.utils.common import (
    INDATAFILE_PREFIX,
    INDIR_NAME,
    OUTDATAFILE_PREFIX,
)
from atomate2.common.files import copy_files, rename_files
from atomate2.utils.file_client import FileClient, auto_fileclient

__all__ = ["out_to_in", "fname2ext", "load_abinit_input"]


logger = logging.getLogger(__name__)


ALL_ABIEXTS = abi_extensions()


def fname2ext(filepath):
    """Get the abinit extension of a given filename.

    This will return None if no extension is found.
    """
    filename = os.path.basename(filepath)
    if "_" not in filename:
        return None
    ext = filename.split("_")[-1].replace(".nc", "")
    if ext not in ALL_ABIEXTS:
        return None
    return ext


@auto_fileclient
def out_to_in(
    out_files: Union[Path, str, Iterable[Union[Path, str]]],
    src_host: str | None = None,
    indir: Path | str = INDIR_NAME,
    file_client: FileClient | None = None,
    link_files: bool = True,
):
    """
    Copy or link an abinit output file to the Abinit input directory.

    Parameters
    ----------
    out_files : str or Path or list
        The abinit output file to be .
    src_host : str or None
        The source hostname used to specify a remote filesystem. Can be given as
        either "username@remote_host" or just "remote_host" in which case the username
        will be inferred from the current user. If ``None``, the local filesystem will
        be used as the source.
    indir : Path or str or None
        The input directory for Abinit input files.
    file_client : .FileClient
        A file client to use for performing file operations.
    link_files : bool
        Whether to link the files instead of copying them.
    """
    if isinstance(out_files, (Path, str)):
        out_files = [out_files]
    for out_file in out_files:
        src_dir = os.path.dirname(out_file)
        out_file = os.path.basename(out_file)
        in_file = out_file.replace(OUTDATAFILE_PREFIX, INDATAFILE_PREFIX, 1)
        in_file = os.path.basename(in_file).replace("WFQ", "WFK", 1)

        # Copy or link previous output files to the input directory and rename them
        copy_files(
            src_dir=src_dir,
            dest_dir=indir,
            src_host=src_host,
            include_files=[out_file],
            file_client=file_client,
            link_files=link_files,
        )
        rename_files(
            filenames={out_file: in_file},
            directory=indir,
            allow_missing=False,
            file_client=file_client,
        )


def load_abinit_input(dirpath, fname="abinit_input.json"):
    abinit_input_file = os.path.join(dirpath, f"{fname}")
    if not os.path.exists(abinit_input_file):
        raise NotImplementedError(
            f"Cannot load AbinitInput from directory without {fname} file."
        )
    abinit_input = loadfn(abinit_input_file)
    return abinit_input
