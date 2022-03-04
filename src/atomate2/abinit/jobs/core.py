"""Core jobs for running ABINIT calculations."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional, Sequence

from abipy.flowtk.utils import irdvars_for_ext

from atomate2.abinit.inputs.factories import (
    NScfInputGenerator,
    NScfWfqInputGenerator,
    RelaxInputGenerator,
    ScfInputGenerator,
)
from atomate2.abinit.jobs.base import BaseAbinitMaker
from atomate2.abinit.utils.common import RestartError

logger = logging.getLogger(__name__)

__all__ = ["ScfMaker", "NonScfMaker"]


@dataclass
class ScfMaker(BaseAbinitMaker):
    """Maker to create ABINIT scf jobs.

    Parameters
    ----------
    name : str
        The job name.
    """

    calc_type: str = "scf"
    name: str = "Scf calculation"
    input_generator: ScfInputGenerator = ScfInputGenerator()
    CRITICAL_EVENTS: Sequence[str] = ("ScfConvergenceWarning",)

    def resolve_restart_deps(self):
        """Resolve dependencies to restart Scf calculations.

        Scf calculations can be restarted from either the WFK file or the DEN file.
        """
        # Prefer WFK over DEN files since we can reuse the wavefunctions.
        if self.restart_info.reset:
            # remove non reset keys that may have been added in a previous restart
            self.remove_restart_vars(["WFK", "DEN"])
        else:
            for ext in ("WFK", "DEN"):
                restart_file = self.restart_info.prev_outdir.has_abiext(ext)
                irdvars = irdvars_for_ext(ext)
                if restart_file:
                    break
            else:
                msg = "Cannot find WFK or DEN file to restart from."
                logger.error(msg)
                raise RestartError(msg)

            # Move out --> in.
            self.out_to_in(restart_file)

            # Add the appropriate variable for restarting.
            self.abinit_input.set_vars(irdvars)


class NonScfDeps(dict):
    def __init__(self):
        super().__init__({"scf": ["DEN"]})


@dataclass
class NonScfMaker(BaseAbinitMaker):
    """Maker to create non SCF calculations."""

    calc_type: str = "nscf"
    name: str = "non-Scf calculation"

    input_generator: NScfInputGenerator = NScfInputGenerator()
    CRITICAL_EVENTS: Sequence[str] = ("NscfConvergenceWarning",)

    # Here there is no way to set a default that is mutable (dict) for the dependencies so I use
    # the default_factory of the dataclass field with a dict subclass...
    # One option could be to use some kind of frozen dict/mapping.
    # - frozendict (https://marco-sulla.github.io/python-frozendict/) is one possibility
    #   but is not part of the stdlib. A PEP was actually discussed (and rejected) to
    #   add such a frozendict in the stdlib (https://www.python.org/dev/peps/pep-0416/).
    # - there is an ongoing PEP being discussed for a frozenmap type in the collections module.
    #   If this PEP (https://www.python.org/dev/peps/pep-0603/) is accepted in the future, we
    #   may think to use this new frozenmap type.
    # Another option would be to use a different structure, e.g. a tuple of tuples. In the current
    # case, this would give : ("scf", ("DEN", )). This is essentially a user defined mapping of course...
    dependencies: Optional[dict] = field(default_factory=NonScfDeps)

    # Non dataclass variables:
    restart_extension = "WFK"

    def resolve_restart_deps(self):
        """Resolve dependencies to restart Non-Scf calculations.

        Non-Scf calculations can only be restarted from the WFK file (or WFQ file).
        """
        if self.restart_info.reset:
            # remove non reset keys that may have been added in a previous restart
            self.remove_restart_vars(["WFQ", "WFK"])
        else:
            ext = self.restart_extension
            restart_file = self.restart_info.prev_outdir.has_abiext(ext)
            if not restart_file:
                msg = f"Cannot find the {self.restart_extension} file to restart from."
                logger.error(msg)
                raise RestartError(msg)

            # Move out --> in.
            self.out_to_in(restart_file)

            # Add the appropriate variable for restarting.
            # Note that the restart of both WFK and WFQ is activated by irdwfk (i.e. ird var for WFK extension)
            irdvars = irdvars_for_ext("WFK")
            self.abinit_input.set_vars(irdvars)


@dataclass
class NonScfWfqMaker(NonScfMaker):
    """Maker to create non SCF calculations for the WFQ."""

    calc_type: str = "nscf_wfq"
    name: str = "non-Scf calculation"

    input_generator: NScfWfqInputGenerator = NScfWfqInputGenerator()
    CRITICAL_EVENTS: Sequence[str] = ("NscfConvergenceWarning",)

    # Here there is no way to set a default that is mutable (dict) for the dependencies so I use
    # the default_factory of the dataclass field with a dict subclass...
    # One option could be to use some kind of frozen dict/mapping.
    # - frozendict (https://marco-sulla.github.io/python-frozendict/) is one possibility
    #   but is not part of the stdlib. A PEP was actually discussed (and rejected) to
    #   add such a frozendict in the stdlib (https://www.python.org/dev/peps/pep-0416/).
    # - there is an ongoing PEP being discussed for a frozenmap type in the collections module.
    #   If this PEP (https://www.python.org/dev/peps/pep-0603/) is accepted in the future, we
    #   may think to use this new frozenmap type.
    # Another option would be to use a different structure, e.g. a tuple of tuples. In the current
    # case, this would give : ("scf", ("DEN", )). This is essentially a user defined mapping of course...
    dependencies: Optional[dict] = field(default_factory=NonScfDeps)

    # Non dataclass variables:
    restart_extension = "WFQ"


@dataclass
class RelaxMaker(BaseAbinitMaker):
    """Maker to create relaxation calculations."""

    calc_type: str = "relax"
    name: str = "Relaxation calculation"

    input_generator: RelaxInputGenerator = RelaxInputGenerator()
    CRITICAL_EVENTS: Sequence[str] = ("RelaxConvergenceWarning",)

    # This is not part of the dataclass __init__ method (hence the purposely absence of annotation)
    structure_fixed = False

    def resolve_restart_deps(self):
        """Resolve dependencies to restart relaxation calculations."""
        if self.restart_info.reset:
            # remove non reset keys that may have been added in a previous restart
            self.remove_restart_vars(["WFK", "DEN"])
        else:
            # for optcell > 0 it may fail to restart if paral_kgb == 0. Do not use DEN or WFK in this case
            # FIXME fix when Matteo makes the restart possible for paral_kgb == 0
            self.abinit_input.get("paral_kgb", 0)
            self.abinit_input.get("optcell", 0)

            # if optcell == 0 or paral_kgb == 1:
            # TODO: see if this works in general (it works for silicon :D)
            #  if not, why not switch by default to paral_kgb = 1 ?
            if True:
                restart_file = None

                # Try to restart from the WFK file if possible.
                # FIXME: This part has been disabled because WFK=IO is a mess if paral_kgb == 1
                # This is also the reason why I wrote my own MPI-IO code for the GW part!
                wfk_file = self.restart_info.prev_outdir.has_abiext("WFK")
                irdvars = None
                if False and wfk_file:
                    irdvars = irdvars_for_ext("WFK")
                    restart_file = self.out_to_in(wfk_file)

                # Fallback to DEN file. Note that here we look for out_DEN instead of out_TIM?_DEN
                # ********************************************************************************
                # Note that it's possible to have an undetected error if we have multiple restarts
                # and the last relax died badly. In this case indeed out_DEN is the file produced
                # by the last run that has executed on_done.
                # ********************************************************************************
                if restart_file is None:
                    out_den = self.restart_info.prev_outdir.path_in("out_DEN")
                    if os.path.exists(out_den):
                        irdvars = irdvars_for_ext("DEN")
                        restart_file = self.out_to_in(out_den)

                if restart_file is None:
                    # Try to restart from the last TIM?_DEN file.
                    # This should happen if the previous run didn't complete in clean way.
                    # Find the last TIM?_DEN file.
                    last_timden = self.restart_info.prev_outdir.find_last_timden_file()
                    if last_timden is not None:
                        if last_timden.path.endswith(".nc"):
                            in_file_name = "in_DEN.nc"
                        else:
                            in_file_name = "in_DEN"
                        restart_file = self.out_to_in_tim(
                            last_timden.path, in_file_name
                        )
                        irdvars = irdvars_for_ext("DEN")

                if restart_file is None:
                    # Don't raise RestartError as the structure has been updated
                    logger.warning(
                        "Cannot find the WFK|DEN|TIM?_DEN file to restart from."
                    )
                else:
                    # Add the appropriate variable for restarting.
                    if irdvars is None:
                        raise RuntimeError("irdvars not set.")
                    self.abinit_input.set_vars(irdvars)
                    logger.info("Will restart from %s", restart_file)

    @classmethod
    def ionic_relaxation(cls):
        """Create an ionic relaxation maker."""
        # TODO: add the possibility to tune the RelaxInputGenerator options in this class method.
        return cls(
            input_generator=RelaxInputGenerator(relax_cell=False),
            name=cls.name + " (ions only)",
        )

    @classmethod
    def full_relaxation(cls):
        """Create a full relaxation maker."""
        # TODO: add the possibility to tune the RelaxInputGenerator options in this class method.
        return cls(input_generator=RelaxInputGenerator(relax_cell=True))
