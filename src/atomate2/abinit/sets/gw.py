"""Module defining Abinit input set generators specific to GW calculations."""

from dataclasses import dataclass
from typing import Optional

from abipy.abio.factories import scr_from_nscfinput, sigma_from_inputs
from abipy.abio.input_tags import NSCF, SCREENING

from atomate2.abinit.files import get_final_structure, load_abinit_input
from atomate2.abinit.sets.base import AbinitInputGenerator

__all__ = [
    "ScreeningSetGenerator",
    "SigmaSetGenerator",
]


@dataclass
class ScreeningSetGenerator(AbinitInputGenerator):
    """Class to generate Abinit Screening input sets."""

    calc_type: str = "scr"

    nband: Optional[int] = None
    ecuteps: Optional[float] = None
    w_type: str = "RPA"
    sc_mode: str = "one_shot"
    hilbert: float = None
    ecutwfn: float = None
    inclvkb: int = 2
    accuracy: str = "normal"

    restart_from_deps: Optional[str] = None
    prev_outputs_deps: tuple = (f"{NSCF}:WFK",)

    def get_abinit_input(
        self,
        structure=None,
        pseudos=None,
        prev_outputs=None,
        nband=nband,
        w_type=w_type,
        ecuteps=ecuteps,
        sc_mode=sc_mode,
        hilbert=hilbert,
        ecutwfn=ecutwfn,
        inclvkb=inclvkb,
        accuracy=accuracy,
    ):
        """Get AbinitInput object for SCR calculation."""
        if prev_outputs is None:
            raise RuntimeError("No previous_outputs. Cannot perform SCR calculation.")
        if len(prev_outputs) != 1:
            raise RuntimeError(
                "Should have exactly one previous output (a NSCF calculation)."
            )
        prev_output = prev_outputs[0]
        previous_abinit_input = load_abinit_input(prev_output)
        previous_structure = get_final_structure(prev_output)
        # TODO: the structure in the previous abinit input may be slightly different
        #  from the one in the previous output (if abinit symmetrizes the structure)
        #  Should we set the structure in the previous_abinit_input ? Or should we
        #  assume that abinit will make the same symmetrization ?
        #  Or should we always symmetrize the structure before ?
        #  Or should we always set tolsym to 1.0e-8 ?
        previous_abinit_input.set_structure(previous_structure)
        if structure is not None:
            if structure != previous_structure:
                raise RuntimeError(
                    "Structure is provided in non-SCF input set generator but "
                    "is not the same as the one from the previous (SCF) input set."
                )

        # Screening.
        abinit_input = scr_from_nscfinput(
            previous_abinit_input,
            nband=nband,
            ecuteps=ecuteps,
            ecutwfn=ecutwfn,
            inclvkb=inclvkb,
            w_type=w_type,
            sc_mode=sc_mode,
            hilbert=hilbert,
            accuracy=accuracy,
        )
        return abinit_input


@dataclass
class SigmaSetGenerator(AbinitInputGenerator):
    """Class to generate Abinit Sigma input sets."""

    calc_type: str = "sigma"

    nband: Optional[int] = None
    ecuteps: Optional[float] = None
    ecutwfn: float = None
    ecutsigx: float = None
    ppmodel: str = "godby"
    gw_qprange: int = 1
    accuracy: str = "normal"

    restart_from_deps: Optional[str] = None
    prev_outputs_deps: tuple = (f"{NSCF}:WFK", f"{SCREENING}:SCR")

    def get_abinit_input(
        self,
        structure=None,
        pseudos=None,
        prev_outputs=None,
        nband=nband,
        ecuteps=ecuteps,
        ecutwfn=ecutwfn,
        ecutsigx=ecutsigx,
        ppmodel=ppmodel,
        gw_qprange=gw_qprange,
        accuracy=accuracy,
    ):
        """Get AbinitInput object for SCR calculation."""
        if prev_outputs is None:
            raise RuntimeError("No previous_outputs. Cannot perform Sigma calculation.")
        if len(prev_outputs) != 2:
            raise RuntimeError(
                "Should have exactly two previous outputs (one NSCF calculation "
                "and one SCREENING calculation)."
            )
        ab1 = load_abinit_input(prev_outputs[0])
        ab2 = load_abinit_input(prev_outputs[1])
        if NSCF in ab1.runlevel and SCREENING in ab2.runlevel:
            nscf_inp = ab1
            scr_inp = ab2
        elif SCREENING in ab1.runlevel and NSCF in ab2.runlevel:
            nscf_inp = ab2
            scr_inp = ab1
        else:
            raise RuntimeError("Could not find one NSCF and one SCREENING calculation.")
        # TODO: do we need to check that the structures are the same in nscf and
        #  screening ?

        previous_structure = get_final_structure(prev_outputs[0])
        # TODO: the structure in the previous abinit input may be slightly different
        #  from the one in the previous output (if abinit symmetrizes the structure)
        #  Should we set the structure in the previous_abinit_input ? Or should we
        #  assume that abinit will make the same symmetrization ?
        #  Or should we always symmetrize the structure before ?
        #  Or should we always set tolsym to 1.0e-8 ?
        nscf_inp.set_structure(previous_structure)
        scr_inp.set_structure(previous_structure)
        if structure is not None:
            if structure != previous_structure:
                raise RuntimeError(
                    "Structure is provided in non-SCF input set generator but "
                    "is not the same as the one from the previous (SCF) input set."
                )

        # Sigma.
        abinit_input = sigma_from_inputs(
            nscf_input=nscf_inp,
            scr_input=scr_inp,
            nband=nband,
            ecutwfn=ecutwfn,
            ecuteps=ecuteps,
            ecutsigx=ecutsigx,
            ppmodel=ppmodel,
            gw_qprange=gw_qprange,
            accuracy=accuracy,
        )

        return abinit_input
