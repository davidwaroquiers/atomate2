"""Functions for manipulating Abinit files."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, Tuple, Union

from abipy.abio.input_tags import MOLECULAR_DYNAMICS, RELAX
from abipy.abio.outputs import AbinitOutputFile
from abipy.electrons import GsrFile
from abipy.flowtk.utils import Directory, File, abi_extensions
from monty.serialization import loadfn
from pymatgen.core.structure import Structure

from atomate2.abinit.utils.common import INDIR_NAME, OUTDIR_NAME, OUTPUT_FILE_NAME
from atomate2.utils.file_client import FileClient, auto_fileclient

__all__ = [
    "out_to_in",
    "fname2ext",
    "load_abinit_input",
    "write_abinit_input_set",
]


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
    out_files: Iterable[Tuple[str, str]],
    src_host: str | None = None,
    indir: Path | str = INDIR_NAME,
    file_client: FileClient | None = None,
    link_files: bool = True,
):
    """
    Copy or link abinit output files to the Abinit input directory.

    Parameters
    ----------
    out_files : list of tuples
        The list of (abinit output filepath, abinit input filename) to be copied
        or linked.
    src_host : str or None
        The source hostname used to specify a remote filesystem. Can be given as
        either "username@remote_host" or just "remote_host" in which case the username
        will be inferred from the current user. If ``None``, the local filesystem will
        be used as the source.
    indir : Path or str
        The input directory for Abinit input files.
    file_client : .FileClient
        A file client to use for performing file operations.
    link_files : bool
        Whether to link the files instead of copying them.
    """
    dest_dir = file_client.abspath(indir, host=None)

    for out_filepath, in_file in out_files:

        src_file = file_client.abspath(out_filepath, host=src_host)
        dest_file = os.path.join(dest_dir, in_file)
        if link_files and src_host is None:
            file_client.link(src_file, dest_file)
        else:
            file_client.copy(src_file, dest_file, src_host=src_host)


def load_abinit_input(dirpath, fname="abinit_input.json"):
    """Load the AbinitInput object from a given directory.

    Parameters
    ----------
    dirpath
        Directory to load the AbinitInput from.
    fname
        Name of the json file containing the AbinitInput.

    Returns
    -------
    AbinitInput
        The AbinitInput object.
    """
    abinit_input_file = os.path.join(dirpath, f"{fname}")
    if not os.path.exists(abinit_input_file):
        raise NotImplementedError(
            f"Cannot load AbinitInput from directory without {fname} file."
        )
    abinit_input = loadfn(abinit_input_file)
    return abinit_input


def write_abinit_input_set(
    structure: Structure,
    input_set_generator,
    prev_outputs=None,
    restart_from=None,
    directory: Union[str, Path] = ".",
):
    """Write the abinit inputs for a given structure using a given generator.

    Parameters
    ----------
    structure
        The structure for which the abinit inputs have to be written.
    input_set_generator
        The input generator used to write the abinit inputs.
    prev_outputs
        The list of previous directories needed for the calculation.
    restart_from
        The previous directory of the same calculation (in case of a restart).
        Note that this should be provided as a list of one directory.
    directory
        Directory in which to write the abinit inputs.
    """
    ais = input_set_generator.get_input_set(
        structure=structure,
        restart_from=restart_from,
        prev_outputs=prev_outputs,
    )
    if not ais.validate():
        raise RuntimeError("AbinitInputSet is not valid.")

    ais.write_input(directory=directory, make_dir=True, overwrite=False)


def get_final_structure(dir_name):
    """Get the final/last structure of a calculation in a given directory.

    This functions tries to get the structure:
    1. from the output file of abinit (run.abo).
    2. from the gsr file of abinit (out_GSR.nc).
    """
    out_path = File(os.path.join(dir_name, OUTPUT_FILE_NAME))
    if out_path.exists:
        try:
            ab_out = AbinitOutputFile.from_file(out_path.path)
            return ab_out.final_structure
        except Exception:
            pass
    gsr_path = Directory(os.path.join(dir_name, OUTDIR_NAME)).has_abiext("GSR")
    if gsr_path:
        # Open the GSR file.
        try:
            gsr_file = GsrFile(gsr_path)
            return gsr_file.structure
        except Exception:
            pass
    abinit_input = load_abinit_input(dirpath=dir_name)
    if len({MOLECULAR_DYNAMICS, RELAX}.intersection(abinit_input.runlevel)) == 0:
        return abinit_input.structure
    raise RuntimeError("Could not get final structure.")
