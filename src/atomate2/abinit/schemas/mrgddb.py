"""Core definitions of Abinit calculations documents."""

import logging
import os
from datetime import datetime
from pathlib import Path

# from typing import Type, TypeVar, Union, Optional, List
from typing import Any, Optional, TypeVar, Union

from abipy.dfpt.ddb import DdbFile
from abipy.flowtk import events
from abipy.flowtk.utils import File
from emmet.core.structure import StructureMetadata
from pydantic import BaseModel, Field
from pymatgen.core.structure import Structure

from atomate2.abinit.schemas.calculation import AbinitObject, TaskState
from atomate2.abinit.utils.common import get_event_report
from atomate2.utils.path import get_uri, strip_hostname

_T = TypeVar("_T", bound="MrgddbTaskDoc")

logger = logging.getLogger(__name__)


class CalculationOutput(BaseModel):
    structure: Union[Structure] = Field(
        None, description="The final structure from the calculation"
    )
    dijk: Optional[list] = Field(
        None, description="Conventional SHG tensor in pm/V (Chi^(2)/2)"
    )
    epsinf: Optional[list] = Field(
        None, description="Electronic contribution to the dielectric tensor"
    )

    @classmethod
    def from_abinit_outddb(
        cls,
        output: DdbFile,
    ):
        structure = output.structure

        dijk = list(output.anaget_nlo(voigt=False, units="pm/V"))
        epsinf = list(output.anaget_epsinf_and_becs()[0])

        return cls(
            structure=structure,
            dijk=dijk,
            epsinf=epsinf,
        )


class Calculation(BaseModel):
    dir_name: str = Field(None, description="The directory for this Abinit calculation")
    abinit_version: str = Field(
        None, description="Abinit version used to perform the calculation"
    )
    has_abinit_completed: TaskState = Field(
        None, description="Whether Abinit completed the calculation successfully"
    )
    output: Optional[CalculationOutput] = Field(
        None, description="The Abinit calculation output"
    )
    completed_at: str = Field(
        None, description="Timestamp for when the calculation was completed"
    )
    event_report: events.EventReport = Field(
        None, description="Event report of this abinit job."
    )
    output_file_paths: Optional[dict[str, str]] = Field(
        None,
        description="Paths (relative to dir_name) of the Abinit output files "
        "associated with this calculation",
    )

    @classmethod
    def from_abinit_files(
        cls,
        dir_name: Path | str,
        task_name: str,
        abinit_outddb_file: Path | str = "out_DDB",
        abinit_mrglog_file: Path | str = "run.log",
    ):
        dir_name = Path(dir_name)
        abinit_outddb_file = dir_name / abinit_outddb_file

        output_doc = None
        if abinit_outddb_file.exists():
            abinit_outddb = DdbFile.from_file(abinit_outddb_file)
            output_doc = CalculationOutput.from_abinit_outddb(abinit_outddb)

            completed_at = str(
                datetime.fromtimestamp(os.stat(abinit_outddb_file).st_mtime)
            )

        report = None
        has_abinit_completed = TaskState.FAILED
        try:
            report = get_event_report(
                ofile=File(abinit_mrglog_file), mpiabort_file=File("whatever")
            )
            if report.run_completed or abinit_outddb_file.exists():
                # VT: abinit_outddb_file should not be necessary but
                # report.run_completed is False even when it completed...
                has_abinit_completed = TaskState.SUCCESS

        except Exception as exc:
            msg = f"{cls} exception while parsing event_report:\n{exc}"
            logger.critical(msg)

        return (
            cls(
                dir_name=str(dir_name),
                task_name=task_name,
                abinit_version=str(abinit_outddb.version),
                has_abinit_completed=has_abinit_completed,
                completed_at=completed_at,
                output=output_doc,
                event_report=report,
            ),
            None,  # abinit_objects,
        )


class OutputDoc(BaseModel):
    structure: Union[Structure] = Field(None, description="The output structure object")
    dijk: Optional[list] = Field(
        None, description="Conventional SHG tensor in pm/V (Chi^(2)/2)"
    )
    epsinf: Optional[list] = Field(
        None, description="Electronic contribution to the dielectric tensor"
    )

    @classmethod
    def from_abinit_calc_doc(cls, calc_doc: Calculation):
        return cls(
            structure=calc_doc.output.structure,
            dijk=calc_doc.output.dijk,
            epsinf=calc_doc.output.epsinf,
        )


class MrgddbTaskDoc(StructureMetadata):
    """Definition of task document about an Mrgddb Job."""

    dir_name: Optional[str] = Field(
        None, description="The directory for this Abinit task"
    )
    completed_at: Optional[str] = Field(
        None, description="Timestamp for when this task was completed"
    )
    output: Optional[OutputDoc] = Field(
        None, description="The output of the final calculation"
    )
    structure: Union[Structure] = Field(
        None, description="Final output atoms from the task"
    )
    state: Optional[TaskState] = Field(None, description="State of this task")
    event_report: Optional[events.EventReport] = Field(
        None, description="Event report of this abinit job."
    )
    included_objects: Optional[list[AbinitObject]] = Field(
        None, description="List of Abinit objects included with this task document"
    )
    abinit_objects: Optional[dict[AbinitObject, Any]] = Field(
        None, description="Abinit objects associated with this task"
    )
    task_label: Optional[str] = Field(None, description="A description of the task")
    tags: Optional[list[str]] = Field(
        None, description="Metadata tags for this task document"
    )

    @classmethod
    def from_directory(
        cls: type[_T],
        dir_name: Path | str,
        additional_fields: dict[str, Any] = None,
        **abinit_calculation_kwargs,
    ):
        """Build MrgddbTaskDoc from directory."""
        logger.info(f"Getting task doc in: {dir_name}")

        if additional_fields is None:
            additional_fields = {}

        dir_name = Path(dir_name)
        task_files = _find_abinit_files(dir_name)

        if len(task_files) == 0:
            raise FileNotFoundError("No Abinit files found!")

        calcs_reversed = []
        all_abinit_objects = []
        for task_name, files in task_files.items():
            calc_doc, abinit_objects = Calculation.from_abinit_files(
                dir_name, task_name, **files, **abinit_calculation_kwargs
            )
            calcs_reversed.append(calc_doc)
            all_abinit_objects.append(abinit_objects)

        tags = additional_fields.get("tags")

        dir_name = get_uri(dir_name)  # convert to full uri path
        dir_name = strip_hostname(
            dir_name
        )  # VT: TODO to put here?necessary with laptop at least...

        # only store objects from last calculation
        # TODO: make this an option
        abinit_objects = all_abinit_objects[-1]
        included_objects = None
        if abinit_objects:
            included_objects = list(abinit_objects.keys())

        # rewrite the original structure save!

        if isinstance(calcs_reversed[-1].output.structure, Structure):
            attr = "from_structure"
            dat = {
                "structure": calcs_reversed[-1].output.structure,
                "meta_structure": calcs_reversed[-1].output.structure,
                "include_structure": True,
            }
        doc = getattr(cls, attr)(**dat)
        ddict = doc.dict()

        data = {
            "abinit_objects": abinit_objects,
            "calcs_reversed": calcs_reversed,
            "completed_at": calcs_reversed[-1].completed_at,
            "dir_name": dir_name,
            "event_report": calcs_reversed[-1].event_report,
            "included_objects": included_objects,
            # "input": InputDoc.from_abinit_calc_doc(calcs_reversed[0]),
            "meta_structure": calcs_reversed[-1].output.structure,
            "output": OutputDoc.from_abinit_calc_doc(calcs_reversed[-1]),
            "state": calcs_reversed[-1].has_abinit_completed,
            "structure": calcs_reversed[-1].output.structure,
            "tags": tags,
        }

        doc = cls(**ddict)
        doc = doc.model_copy(update=data)
        return doc.model_copy(update=additional_fields, deep=True)


def _find_abinit_files(
    path: Path | str,
) -> dict[str, Any]:
    """Find Abinit files"""
    path = Path(path)
    task_files = {}

    def _get_task_files(files: list[Path], suffix: str = "") -> dict:
        abinit_files = {}
        for file in files:
            # Here we make assumptions about the output file naming
            if file.match(f"*outdata/out_DDB{suffix}*"):
                abinit_files["abinit_outddb_file"] = Path(file).relative_to(path)
            elif file.match(f"*run.log{suffix}*"):
                abinit_files["abinit_mrglog_file"] = Path(file).relative_to(path)

        return abinit_files

    # get any matching file from the root folder
    standard_files = _get_task_files(
        list(path.glob("*")) + list(path.glob("outdata/*"))
    )
    if len(standard_files) > 0:
        task_files["standard"] = standard_files

    return task_files