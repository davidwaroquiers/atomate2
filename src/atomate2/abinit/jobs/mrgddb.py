"""Merge DDB jobs for merging DDB files from ABINIT calculations."""

from __future__ import annotations

import itertools
import logging
import os
from dataclasses import dataclass, field
from typing import ClassVar, Sequence

from abipy.abio.inputs import AbinitInput
from abipy.flowtk.utils import Directory
from jobflow import Flow, Maker, Response, job
from pymatgen.core.structure import Structure

from atomate2 import SETTINGS
from atomate2.abinit.files import write_mrgddb_input_set
from atomate2.abinit.jobs.base import BaseAbinitMaker, setup_job
from atomate2.abinit.powerups import update_user_abinit_settings
from atomate2.abinit.run import run_mrgddb
from atomate2.abinit.schemas.core import AbinitTaskDocument, Status
from atomate2.abinit.schemas.mrgddb import MrgddbTaskDocument
from atomate2.abinit.sets.mrgddb import (
    MrgddbInputGenerator,
    MrgddbSetGenerator,
)
from atomate2.abinit.utils.common import OUTDIR_NAME
from atomate2.abinit.utils.history import JobHistory

logger = logging.getLogger(__name__)

__all__ = [
    "MrgddbMaker",
]


@dataclass
class MrgddbMaker(Maker):
    """Maker to create a job with a merge of DDB files from ABINIT.

    Parameters
    ----------
    name : str
        The job name.
    """
    
    #_calc_type: str = "mrgddb_merge" #VT need to remove this because of the @property below
    # would have been okay in a child class with @dataclass
    name: str = "Merge DDB"
    input_set_generator: MrgddbInputGenerator = field(default_factory=MrgddbSetGenerator)
    #input_set_generator: MrgddbInputGenerator = MrgddbSetGenerator()
    wall_time: int | None = None

    # TODO: is there a critical events for this?
    #CRITICAL_EVENTS: ClassVar[Sequence[str]] = ("NscfConvergenceWarning",)
    # class variables
    #CRITICAL_EVENTS: ClassVar[Sequence[str]] = ("ScfConvergenceWarning",)
    CRITICAL_EVENTS: ClassVar[Sequence[str]] = ()

    def __post_init__(self):
        """Process post-init configuration."""
        self.critical_events = [
            as_event_class(ce_name) for ce_name in self.CRITICAL_EVENTS
        ]

    @property
    def calc_type(self):
        """Get the type of calculation for this maker."""
        return self.input_set_generator.calc_type


    @job
    def make(
        self,
        prev_outputs: str | Path | list[str] | None = None,
        restart_from: str | Path | list[str] | None = None,
        history: JobHistory | None = None,
    ) -> jobflow.Flow | jobflow.Job:
        """
        Return a MRGDDB jobflow.Job.

        Parameters
        ----------
        prev_outputs : TODO: add description from sets.base
        restart_from : TODO: add description from sets.base
        history : JobHistory
            A JobHistory object containing the history of this job.
        """
        # Flatten the list of previous outputs dir
        prev_outputs = [item for sublist in prev_outputs for item in sublist]

        # Setup job and get general job configuration
        config = setup_job(
            structure=None,
            prev_outputs=prev_outputs,
            restart_from=restart_from,
            history=history,
            wall_time=self.wall_time,
        )

        # Write mrgddb input set
        write_mrgddb_input_set(
            input_set_generator=self.input_set_generator,
            prev_outputs=prev_outputs,
            restart_from=restart_from,
            directory=config.workdir,
        )

        # Run mrgddb
        run_status = run_mrgddb(
            wall_time=config.wall_time,
            start_time=config.start_time,
        )

        # parse Mrgddb DDB output
        run_number = config.history.run_number
        task_doc = MrgddbTaskDocument.from_directory( # TODO: MrgddbTaskDocument ?
            config.workdir,
            critical_events=self.critical_events,
            run_number=run_number,
            run_status=run_status,
        )
        task_doc.task_label = self.name

        return self.get_response(
            task_document=task_doc,
            history=config.history,
            max_restarts=SETTINGS.ABINIT_MAX_RESTARTS,
            prev_outputs=prev_outputs,
        )

    def get_response(
        self,
        task_document: MrgddbTaskDocument, #TODO: MrgddbTaskDocument ?
        history: JobHistory,
        max_restarts: int = 5,
        prev_outputs: str | tuple | list | Path | None = None,
    ):
        """Get new job to restart mrgddb calculation."""
        if task_document.state == Status.SUCCESS:
            return Response(
                output=task_document,
            )

        #if history.run_number > max_restarts:
        #    # TODO: check here if we should stop jobflow or children or
        #    #  if we should throw an error.
        #    unconverged_error = UnconvergedError(
        #        self,
        #        msg=f"Unconverged after {history.run_number} runs.",
        #        mrgddb_input=task_document.mrgddb_input,
        #        history=history,
        #    )
        #    return Response(
        #        output=task_document,
        #        stop_children=True,
        #        stop_jobflow=True,
        #        stored_data={"error": unconverged_error},
        #    )

        logger.info("Getting restart job.")

        new_job = self.make(
            structure=task_document.structure,
            restart_from=task_document.dir_name,
            prev_outputs=prev_outputs,
            history=history,
        )

        return Response(
            output=task_document,
            replace=new_job,
        )