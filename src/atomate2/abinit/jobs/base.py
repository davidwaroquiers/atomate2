"""Definition of base ABINIT job maker."""

from __future__ import annotations

import logging
import os
import time
from collections import namedtuple
from dataclasses import dataclass
from typing import Any, ClassVar, List, Optional, Sequence, Union

import jobflow

# from abipy.flowtk.events import AbinitEvent
from abipy.flowtk.events import as_event_class
from jobflow import Maker, Response, job
from monty.json import jsanitize
from monty.serialization import dumpfn
from pymatgen.core.structure import Structure

from atomate2.abinit.files import write_abinit_input_set
from atomate2.abinit.run import run_abinit
from atomate2.abinit.schemas.core import AbinitTaskDocument, Status
from atomate2.abinit.sets.base import AbinitInputSetGenerator
from atomate2.abinit.utils.common import InitializationError, UnconvergedError
from atomate2.abinit.utils.history import JobHistory
from atomate2.settings import Atomate2Settings

logger = logging.getLogger(__name__)

__all__ = ["BaseAbinitMaker"]


ResponseArgs = namedtuple(
    "ResponseArgs",
    ["detour", "addition", "replace", "stop_children", "stop_jobflow", "stored_data"],
)


JobSetupVars = namedtuple(
    "JobSetupVars",
    ["start_time", "history", "workdir", "settings", "abipy_manager", "wall_time"],
)


def setup_job(
    structure,
    prev_outputs,
    restart_from,
    history,
    wall_time,
):
    # Get the start time.
    start_time = time.time()

    if structure is None and prev_outputs is None and restart_from is None:
        raise RuntimeError(
            "At least one of structure, prev_outputs or "
            "restart_from should be defined."
        )

    if history is None:
        # Supposedly the first time the job is created
        history = JobHistory()
    elif restart_from is not None:
        # We want to log the restart only if the restart_from is due to
        # an automatic restart, not a restart from e.g. another scf or relax
        # with different parameters.
        history.log_restart()

    # Set up working directory
    workdir = os.getcwd()

    # Log information about the start of the job
    history.log_start(workdir=workdir, start_time=start_time)

    # Set up logging
    log_handler = logging.FileHandler("atomate2_abinit.log")
    log_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    logging.getLogger("pymatgen.io.abinit").addHandler(log_handler)
    logging.getLogger("abipy").addHandler(log_handler)
    logging.getLogger("atomate2").addHandler(log_handler)

    # Load the atomate settings for abinit to get configuration parameters
    # TODO: how to allow for tuned parameters on a per-job basis ?
    #  (similar to fw_spec-passed settings)
    settings = Atomate2Settings()
    abipy_manager = None  # Currently disabled as it is needed for autoparal,
    # which is not yet supported
    # abipy_manager = get_abipy_manager(settings)

    # set walltime, if possible
    # TODO: see in set_walltime, where to put this walltime_command
    wall_time = wall_time
    return JobSetupVars(
        start_time=start_time,
        history=history,
        workdir=workdir,
        settings=settings,
        abipy_manager=abipy_manager,
        wall_time=wall_time,
    )


@dataclass
class BaseAbinitMaker(Maker):
    """
    Base ABINIT job maker.

    Parameters
    ----------
    name : str
        The job name.
    pseudos : list of str, PseudoTable
        The pseudopotentials to use.
    """

    input_set_generator: AbinitInputSetGenerator
    name: str = "base abinit job"
    wall_time: Optional[int] = None

    # class variables
    CRITICAL_EVENTS: ClassVar[Sequence[str]] = ()
    structure_fixed: ClassVar[bool] = True

    @classmethod
    def from_params(
        cls,
        input_set_generator=None,
        name=None,
        wall_time=wall_time,
        **kwargs,
    ):
        name = name or cls.name
        input_set_generator = input_set_generator or cls.input_set_generator
        ret = cls(
            input_set_generator=input_set_generator,
            name=name,
            wall_time=wall_time,
        )
        for param, value in kwargs.items():
            ret.input_set_generator.__setattr__(param, value)
        return ret

    def __post_init__(self):
        """Process post-init configuration."""
        self.critical_events = [
            as_event_class(ce_name) for ce_name in self.CRITICAL_EVENTS
        ]
        if self.input_set_generator is None:
            raise InitializationError("Input set generator is not set.")

    @property
    def calc_type(self):
        return self.input_set_generator.calc_type

    @job
    def make(
        self,
        structure: Optional[Structure] = None,
        prev_outputs: Optional[Any] = None,
        restart_from: Optional[Union[str]] = None,
        history: Optional[JobHistory] = None,
    ) -> Union[jobflow.Flow, jobflow.Job]:
        """
        Return an ABINIT jobflow.Job.

        Parameters
        ----------
        structure : Structure
            A pymatgen structure object.
        prev_outputs : TODO: add description from sets.base
        restart_from : TODO: add description from sets.base
        history : JobHistory
            A JobHistory object containing the history of this job.
        """
        # Setup job and get general job configuration
        job_config = setup_job(
            structure=structure,
            prev_outputs=prev_outputs,
            restart_from=restart_from,
            history=history,
            wall_time=self.wall_time,
        )

        # Write abinit input set
        write_abinit_input_set(
            structure=structure,
            input_set_generator=self.input_set_generator,
            prev_outputs=prev_outputs,
            restart_from=restart_from,
            directory=job_config.workdir,
        )

        # Run abinit
        run_abinit(
            abinit_cmd=job_config.settings.ABINIT_CMD,
            mpirun_cmd=job_config.settings.ABINIT_MPIRUN_CMD,
            wall_time=job_config.wall_time,
        )

        # parse Abinit outputs
        run_number = job_config.history.run_number
        task_doc = AbinitTaskDocument.from_directory(
            job_config.workdir,
            critical_events=self.critical_events,
            run_number=run_number,
            structure_fixed=self.structure_fixed,
        )
        task_doc.task_label = self.name

        response_args = self.get_response_args(
            task_document=task_doc,
            history=job_config.history,
            max_restarts=job_config.settings.ABINIT_MAX_RESTARTS,
            prev_outputs=prev_outputs,
        )

        dumpfn(jsanitize(task_doc.dict()), fn="task_document.json", indent=2)

        return Response(
            output=task_doc,
            detour=response_args.detour,
            addition=response_args.addition,
            replace=response_args.replace,
            stop_children=response_args.stop_children,
            stop_jobflow=response_args.stop_jobflow,
            stored_data=response_args.stored_data,
        )

    def get_response_args(
        self,
        task_document: AbinitTaskDocument,
        history: JobHistory,
        max_restarts: int = 5,
        prev_outputs: Optional[List[str]] = None,
    ):
        """Get new job to restart abinit calculation."""
        if task_document.state == Status.SUCCESS:
            return ResponseArgs(
                detour=None,
                addition=None,
                replace=None,
                stop_children=False,
                stop_jobflow=False,
                stored_data=None,
            )

        if history.run_number > max_restarts:
            # TODO: check here if we should stop jobflow or children or
            #  if we should throw an error.
            unconverged_error = UnconvergedError(
                self,
                msg="Unconverged after {} runs.".format(history.run_number),
                abinit_input=task_document.abinit_input,
                history=history,
            )
            return ResponseArgs(
                detour=None,
                addition=None,
                replace=None,
                stop_children=True,
                stop_jobflow=True,
                stored_data={"error": unconverged_error},
            )

        logger.info(msg="Getting restart job.")

        new_job = self.make(
            structure=task_document.structure,
            restart_from=task_document.dir_name,
            prev_outputs=prev_outputs,
            history=history,
        )

        return ResponseArgs(
            detour=None,
            addition=None,
            replace=new_job,
            stop_children=False,
            stop_jobflow=False,
            stored_data=None,
        )
