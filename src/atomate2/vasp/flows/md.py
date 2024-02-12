"""Flows for running molecular dynamics simulations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from jobflow import Flow, Maker, OutputReference

from atomate2.vasp.jobs.md import MDMaker, MLMDMaker, md_output
from atomate2.vasp.sets.core import MDSetGenerator

if TYPE_CHECKING:
    from pathlib import Path

    from pymatgen.core import Structure

    from atomate2.vasp.jobs.base import BaseVaspMaker


@dataclass
class MultiMDMaker(Maker):
    """
    Maker to perform an MD run split in several steps.

    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    md_makers : .BaseVaspMaker
        Maker to use to generate the first relaxation.
    """

    name: str = "multi md"
    md_makers: list[BaseVaspMaker] = field(default_factory=lambda: [MDMaker()])

    def make(
        self,
        structure: Structure,
        prev_dir: str | Path | None = None,
        prev_traj_ids: list[str] | None = None,
    ) -> Flow:
        """
        Create a flow with several chained MD runs.

        Parameters
        ----------
        structure : .Structure
            A pymatgen structure object.
        prev_dir : str or Path or None
            A previous VASP calculation directory to copy output files from.
        prev_traj_ids: a list of ids of job identifying previous steps of the
            MD trajectory.

        Returns
        -------
        Flow
            A flow containing n_runs MD calculations.
        """
        md_job = None
        md_jobs = []
        for i, maker in enumerate(self.md_makers, 1):
            if md_job is None:
                md_structure = structure
                md_prev_dir = prev_dir
            else:
                md_structure = md_job.output.structure
                md_prev_dir = md_job.output.dir_name
            md_job = maker.make(md_structure, prev_dir=md_prev_dir)
            md_job.name += f" {i}"
            md_jobs.append(md_job)

        output_job = md_output(
            structure=md_jobs[-1].output.structure,
            vasp_dir=md_jobs[-1].output.dir_name,
            traj_ids=[j.uuid for j in md_jobs],
            prev_traj_ids=prev_traj_ids,
        )
        output_job.name = "molecular dynamics output"

        md_jobs.append(output_job)

        return Flow(md_jobs, output_job.output, name=self.name)

    def restart_from_uuid(self, md_ref: str | OutputReference) -> Flow:
        """
        Create a flow from the output reference of another MultiMDMaker.

        The last output will be used as the starting point and the reference to
        all the previous steps will be included in the final document.

        Parameters
        ----------
        md_ref: str or OutputReference
            The reference to the output of another MultiMDMaker

        Returns
        -------
            A flow containing n_runs MD calculations.
        """
        if isinstance(md_ref, str):
            md_ref = OutputReference(md_ref)

        return self.make(
            structure=md_ref.structure,
            prev_dir=md_ref.vasp_dir,
            prev_traj_ids=md_ref.full_traj_ids,
        )

    @staticmethod
    def _split_md(
        nsteps: int, n_runs: int, start_temp: float, end_temp: float | None = None
    ) -> list:
        if end_temp is None:
            end_temp = start_temp
        # Split steps into balanced groups
        nsteps_run = nsteps // n_runs
        remaining = nsteps - n_runs * nsteps_run
        nsteps_runs = [nsteps_run] * n_runs
        for ii in range(remaining):
            nsteps_runs[ii] += 1

        # Adapt start and end temperatures to the number of steps in each run
        delta_temp = end_temp - start_temp
        start_temp_runs = []
        end_temp_runs = []
        prevrun_end_temp = start_temp
        for irun in range(n_runs):
            start_temp_runs.append(prevrun_end_temp)
            prevrun_end_temp += delta_temp / nsteps * nsteps_runs[irun]
            end_temp_runs.append(prevrun_end_temp)

        return list(zip(nsteps_runs, start_temp_runs, end_temp_runs))

    @classmethod
    def from_parameters(
        cls,
        nsteps: int,
        time_step: float,
        n_runs: int,
        ensemble: str,
        start_temp: float,
        end_temp: float | None = None,
        **kwargs,
    ) -> MultiMDMaker:
        """
        Create an instance of the Maker based on the standard parameters.

        Set values in the Flow maker, the Job Maker and the VaspInputGenerator,
        using them to create the final instance of the Maker.

        Parameters
        ----------
        nsteps: int
            Number of time steps for simulations. The VASP `NSW` parameter.
        time_step: float
            The time step (in femtosecond) for the simulation. The VASP
            `POTIM` parameter.
        n_runs : int
            Number of MD runs in the flow.
        ensemble: str
            Molecular dynamics ensemble to run. Options include `nvt`, `nve`, and `npt`.
        start_temp: float
            Starting temperature. The VASP `TEBEG` parameter.
        end_temp: float or None
            Final temperature. The VASP `TEEND` parameter. If None the same
            as start_temp.
        kwargs:
            Other parameters passed

        Returns
        -------
            A MultiMDMaker
        """
        md_makers = []
        for nsteps_run, start_temp_run, end_temp_run in cls._split_md(
            nsteps=nsteps, n_runs=n_runs, start_temp=start_temp, end_temp=end_temp
        ):
            generator = MDSetGenerator(
                nsteps=nsteps_run,
                time_step=time_step,
                ensemble=ensemble,
                start_temp=start_temp_run,
                end_temp=end_temp_run,
            )
            md_makers.append(MDMaker(input_set_generator=generator))
        return cls(md_makers=md_makers, **kwargs)

    @classmethod
    def onthefly_mlff(
        cls,
        nsteps: int,
        time_step: float,
        n_runs: int,
        ensemble: str,
        start_temp: float,
        end_temp: float | None = None,
        **kwargs,
    ) -> MultiMDMaker:
        """
        Create an instance of the Maker based on the standard parameters.

        Set values in the Flow maker, the Job Maker and the VaspInputGenerator,
        using them to create the final instance of the Maker.

        Parameters
        ----------
        nsteps: int
            Number of time steps for simulations. The VASP `NSW` parameter.
        time_step: float
            The time step (in femtosecond) for the simulation. The VASP
            `POTIM` parameter.
        n_runs : int
            Number of MD runs in the flow.
        ensemble: str
            Molecular dynamics ensemble to run. Options include `nvt`, `nve`, and `npt`.
        start_temp: float
            Starting temperature. The VASP `TEBEG` parameter.
        end_temp: float or None
            Final temperature. The VASP `TEEND` parameter. If None the same
            as start_temp.
        kwargs:
            Other parameters passed

        Returns
        -------
            A MultiMDMaker
        """
        md_makers = []
        for nsteps_run, start_temp_run, end_temp_run in cls._split_md(
            nsteps=nsteps, n_runs=n_runs, start_temp=start_temp, end_temp=end_temp
        ):
            md_makers.append(
                MLMDMaker.train(
                    generator_kwargs={
                        "nsteps": nsteps_run,
                        "time_step": time_step,
                        "ensemble": ensemble,
                        "start_temp": start_temp_run,
                        "end_temp": end_temp_run,
                    },
                )
            )
        return cls(md_makers=md_makers, **kwargs)
