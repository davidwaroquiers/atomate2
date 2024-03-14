"""DFPT abinit flow makers."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jobflow import Flow, Maker
from pymatgen.core.structure import Structure

from atomate2.abinit.jobs.base import BaseAbinitMaker
from atomate2.abinit.jobs.core import (
    StaticMaker,
)
from atomate2.abinit.jobs.mrgddb import (
    MrgddbMaker,
)
from atomate2.abinit.jobs.response import (
    DdeMaker,
    DdkMaker,
    DteMaker,
    generate_dde_perts,
    generate_ddk_perts,
    generate_dte_perts,
    run_dde_rf,
    run_ddk_rf,
    run_dte_rf,
)
from atomate2.abinit.powerups import (
    update_factory_kwargs,
    update_user_abinit_settings,
    update_user_kpoints_settings
)


@dataclass
class DfptFlowMaker(Maker):
    """
    Maker to generate a DFPT flow with abinit.

    The classmethods allow to tailor the flow for specific properties
        accessible via DFPT.

    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    scf_maker : .BaseAbinitMaker
        The maker to use for the static calculation.
    ddk_maker : .BaseAbinitMaker
        The maker to use for the DDK calculations.
    dde_maker : .BaseAbinitMaker
        The maker to use for the DDE calculations.
    dte_maker : .BaseAbinitMaker
        The maker to use for the DTE calculations.
    mrgddb_maker : .Maker
        The maker to merge the DDE and DTE DDB.
    use_ddk_sym : bool
        True if only the irreducible DDK perturbations should be considered,
            False otherwise.
    use_dde_sym : bool
        True if only the irreducible DDE perturbations should be considered,
            False otherwise.
    dte_skip_permutations: Since the current version of abinit always performs
        all the permutations of the perturbations, even if only one is asked,
        if True avoids the creation of inputs that will produce duplicated outputs.
    dte_phonon_pert: is True also the phonon perturbations will be considered.
        Default False.
    dte_ixc: Value of ixc variable. Used to overwrite the default value read
        from pseudos.
    """

    name: str = "DFPT"
    static_maker: BaseAbinitMaker = field(default_factory=StaticMaker)
    ddk_maker: BaseAbinitMaker | None = field(default_factory=DdkMaker)  # |
    dde_maker: BaseAbinitMaker | None = field(
        default_factory=DdeMaker
    )  # | VT: replace by bool?
    dte_maker: BaseAbinitMaker | None = field(default_factory=DteMaker)  # |
    mrgddb_maker: Maker | None = None #field(default_factory=MrgddbMaker)  # |
    use_ddk_sym: bool | None = False
    use_dde_sym: bool | None = False
    dte_skip_permutations: bool | None = False
    dte_phonon_pert: bool | None = False
    dte_ixc: int | None = None

    def make(
        self,
        structure: Structure | None = None,
        restart_from: str | Path | None = None,
    ):
        """
        Create a DFPT flow.

        Parameters
        ----------
        structure : Structure
            A pymatgen structure object.
        restart_from : str or Path or None
            One previous directory to restart from.

        Returns
        -------
        Flow
            A DFPT flow
        """
        static_job = self.static_maker.make(structure, restart_from=restart_from)
        #To avoid metallic case=occopt=3 which is not okay wrt. DFPT and occopt 1 with spin polarization requires spinmagntarget
        static_job = update_factory_kwargs(         static_job, {'smearing': 'nosmearing', 'spin_mode': 'unpolarized'})
        static_job = update_user_kpoints_settings(  static_job, {"grid_density": 3000})
        static_job = update_user_abinit_settings(   static_job, {   'nstep': 500,
                                                                    'toldfe': 1e-22,
                                                                    'autoparal': 1,
                                                                    'npfft': 1,
                                                                    'chksymbreak': '0'})
        jobs = [static_job]

        if self.ddk_maker:
            # generate the perturbations for the DDK calculations
            ddk_perts = generate_ddk_perts(
                gsinput=static_job.output.abinit_input,
                use_symmetries=self.use_ddk_sym,
            )
            jobs.append(ddk_perts)

            # perform the DDK calculations
            ddk_calcs = run_ddk_rf(
                perturbations=ddk_perts.output,
                prev_outputs=static_job.output.dir_name,
                structure=structure,
            )
            jobs.append(ddk_calcs)

        if self.dde_maker:
            # generate the perturbations for the DDE calculations
            dde_perts = generate_dde_perts(
                gsinput=static_job.output.abinit_input,
                use_symmetries=self.use_dde_sym,
            )
            jobs.append(dde_perts)

            # perform the DDE calculations
            dde_calcs = run_dde_rf(
                perturbations=dde_perts.output,
                prev_outputs=[[static_job.output.dir_name], ddk_calcs.output['dirs']],
                structure=structure,
            )
            jobs.append(dde_calcs)

        if self.dte_maker:
            # generate the perturbations for the DTE calculations
            dte_perts = generate_dte_perts(
                gsinput=static_job.output.abinit_input,
                skip_permutations=self.dte_skip_permutations,
                phonon_pert=self.dte_phonon_pert,
                ixc=self.dte_ixc,
            )
            jobs.append(dte_perts)

            # perform the DTE calculations
            dte_calcs = run_dte_rf(
                perturbations=dte_perts.output,
                prev_outputs=[
                    [static_job.output.dir_name],
                    #ddk_calcs.output["dirs"], #not sure this is needed
                    dde_calcs.output["dirs"]],
                structure=structure,
            )
            jobs.append(dte_calcs)

        if self.mrgddb_maker:
            #merge the DDE and DTE DDB.
            
            prev_outputs = [dde_calcs.output["dirs"], dte_calcs.output["dirs"]]
            
            mrgddb_job = self.mrgddb_maker.make(
                prev_outputs=prev_outputs,
            )
            
            jobs.append(mrgddb_job)

        # TODO: implement the possibility of other DFPT WFs (phonons,...)
        # if self.wfq_maker:
        #     ...

        return Flow(jobs, output=jobs[-1].output, name=self.name)  # TODO: fix outputs

    @classmethod
    def shg(cls, *args, **kwargs):
        """Chi2 SHG.

        Create a DFPT flow to compute the static nonlinear optical
            susceptibility tensor for the second-harmonic generation.

        """
        ddk_maker = DdkMaker()
        dde_maker = DdeMaker()
        dte_maker = DteMaker()
        mrgddb_maker = MrgddbMaker()
        return cls(
            name="Chi2 SHG",
            ddk_maker=ddk_maker,
            dde_maker=dde_maker,
            dte_maker=dte_maker,
            mrgddb_maker=mrgddb_maker,
            use_ddk_sym=False,
            use_dde_sym=False,
            dte_skip_permutations=False,
            dte_phonon_pert=False,
            dte_ixc=None,  # TODO: enforce LDA or not ?
        )