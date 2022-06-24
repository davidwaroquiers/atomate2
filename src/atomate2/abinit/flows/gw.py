"""Core abinit flow makers."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from jobflow import Flow, Maker
from pymatgen.core.structure import Structure

from atomate2.abinit.jobs.core import NonSCFMaker, StaticMaker
from atomate2.abinit.jobs.gw import ScreeningMaker, SigmaMaker


@dataclass
class G0W0Maker(Maker):
    """
    Maker to generate G0W0 flows.
    """

    name: str = "G0W0 calculation"
    scf_maker: StaticMaker = field(default_factory=StaticMaker)
    nscf_maker: NonSCFMaker = field(default_factory=NonSCFMaker)
    scr_maker: ScreeningMaker = field(default_factory=ScreeningMaker)
    sigma_maker: SigmaMaker = field(default_factory=SigmaMaker)

    def __post_init__(self):
        # TODO: make some checks on the input sets, e.g.:
        #  - non scf has to be uniform
        #  - set istwfk ? or check that it is "*1" ?
        #  - kpoint shifts ?
        #  - check nbands in nscf is >= nband in screening and sigma
        pass

    def make(
        self,
        structure: Structure,
        restart_from: Optional[Union[str, Path]] = None,
    ):
        """
        Create a G0W0 flow.

        Parameters
        ----------
        structure : Structure
            A pymatgen structure object.
        restart_from : str or Path or None
            One previous directory to restart from.

        Returns
        -------
        Flow
            A G0W0 flow.
        """

        scf_job = self.scf_maker.make(structure, restart_from=restart_from)
        nscf_job = self.nscf_maker.make(
            prev_outputs=scf_job.output.dir_name, mode="uniform"
        )
        scr_job = self.scr_maker.make(prev_outputs=nscf_job.output.dir_name)
        sigma_job = self.sigma_maker.make(
            prev_outputs=[nscf_job.output.dir_name, scr_job.output.dir_name]
        )

        return Flow([scf_job, nscf_job, scr_job, sigma_job], name=self.name)


@dataclass
class G0W0ConvergenceMaker(Maker):
    """
    Maker to generate convergence of G0W0 calculations.
    """

    name: str = "G0W0 calculation"
    scf_maker: StaticMaker = field(default_factory=StaticMaker)
    nscf_maker: NonSCFMaker = field(default_factory=NonSCFMaker)
    scr_makers: List[ScreeningMaker] = field(default_factory=lambda: [ScreeningMaker()])
    sigma_makers: List[SigmaMaker] = field(default_factory=lambda: [SigmaMaker()])

    def __post_init__(self):
        # TODO: make some checks on the input sets, e.g.:
        #  - non scf has to be uniform
        #  - set istwfk ? or check that it is "*1" ?
        #  - kpoint shifts ?
        pass

    def make(
        self,
        structure: Structure,
        restart_from: Optional[Union[str, Path]] = None,
    ):
        """
        Create a convergence G0W0 flow.

        Parameters
        ----------
        structure : Structure
            A pymatgen structure object.
        restart_from : str or Path or None
            One previous directory to restart from.

        Returns
        -------
        Flow
            A G0W0 flow.
        """

        scf_job = self.scf_maker.make(structure, restart_from=restart_from)
        nscf_job = self.nscf_maker.make(
            prev_outputs=scf_job.output.dir_name, mode="uniform"
        )
        jobs = [scf_job, nscf_job]
        for scr_maker in self.scr_makers:
            scr_job = scr_maker.make(prev_outputs=nscf_job.output.dir_name)
            jobs.append(scr_job)
            for sigma_maker in self.sigma_makers:
                sigma_job = sigma_maker.make(
                    prev_outputs=[nscf_job.output.dir_name, scr_job.output.dir_name]
                )
                jobs.append(sigma_job)

        return Flow(jobs, name=self.name)
