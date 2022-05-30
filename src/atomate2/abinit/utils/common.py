"""Module with common file names and classes used for Abinit flows."""

import os

from abipy.flowtk.utils import Directory
from monty.json import MSONable
from monty.serialization import MontyDecoder
from pymatgen.util.serialization import pmg_serialize

TMPDIR_NAME = "tmpdata"
OUTDIR_NAME = "outdata"
INDIR_NAME = "indata"
TMPDATAFILE_PREFIX = "tmp"
OUTDATAFILE_PREFIX = "out"
INDATAFILE_PREFIX = "in"
TMPDATA_PREFIX = os.path.join(TMPDIR_NAME, TMPDATAFILE_PREFIX)
OUTDATA_PREFIX = os.path.join(OUTDIR_NAME, OUTDATAFILE_PREFIX)
INDATA_PREFIX = os.path.join(INDIR_NAME, INDATAFILE_PREFIX)
STDERR_FILE_NAME = "run.err"
LOG_FILE_NAME = "run.log"
OUTPUT_FILE_NAME = "run.abo"
OUTNC_FILE_NAME = "out_OUT.nc"
INPUT_FILE_NAME = "run.abi"
MPIABORTFILE = "__ABI_MPIABORTFILE__"
DUMMY_FILENAME = "__DUMMY__"
ELPHON_OUTPUT_FILE_NAME = "run.abo_elphon"
DDK_FILES_FILE_NAME = "ddk.files"
HISTORY_JSON = "history.json"

# # Prefixes for Abinit (input, output, temporary) files.
#     Prefix = namedtuple("Prefix", "idata odata tdata")
#     pj = os.path.join
#
#     prefix = Prefix(pj("indata", "in"), pj("outdata", "out"), pj("tmpdata", "tmp"))


class ErrorCode(object):
    """Error code to classify the errors."""

    ERROR = "Error"
    UNRECOVERABLE = "Unrecoverable"
    UNCLASSIFIED = "Unclassified"
    UNCONVERGED = "Unconverged"
    UNCONVERGED_PARAMETERS = "Unconverged_parameters"
    INITIALIZATION = "Initialization"
    RESTART = "Restart"
    POSTPROCESS = "Postprocess"
    WALLTIME = "Walltime"


class AbiAtomateError(Exception):
    """Base class for the abinit errors in atomate."""

    def __init__(self, msg):
        super().__init__(msg)
        self.msg = msg

    def to_dict(self):
        """Create dictionary representation of the error."""
        return dict(error_code=self.ERROR_CODE, msg=self.msg)


class AbinitRuntimeError(AbiAtomateError):
    """Exception raised for errors during Abinit calculation.

    Contains the information about the errors and warning extracted from the output files.
    Initialized with a job, uses it to prepare a suitable error message.
    """

    ERROR_CODE = ErrorCode.ERROR

    def __init__(
        self,
        job=None,
        msg=None,
        num_errors=None,
        num_warnings=None,
        errors=None,
        warnings=None,
    ):
        """Construct AbinitRuntimeError object.

        If the job has a report all the information will be extracted from it, otherwise the arguments will be used.

        Parameters
        ----------
        job
            the atomate2 job
        msg
            the error message
        num_errors
            number of errors in the abinit execution. Only used if job doesn't have a report.
        num_warnings
            number of warning in the abinit execution. Only used if job doesn't have a report.
        errors
            list of errors in the abinit execution. Only used if job doesn't have a report.
        warnings
            list of warnings in the abinit execution. Only used if job doesn't have a report.
        """
        # This can handle both the cases of DECODE_MONTY=True and False (Since it has a from_dict method).
        super().__init__(msg)
        self.job = job
        if (
            self.job is not None
            and hasattr(self.job, "report")
            and self.job.report is not None
        ):
            report = self.job.report
            self.num_errors = report.num_errors
            self.num_warnings = report.num_warnings
            self.errors = report.errors
            self.warnings = report.warnings
        else:
            self.num_errors = num_errors
            self.num_warnings = num_warnings
            self.errors = errors
            self.warnings = warnings
        self.msg = msg

    @pmg_serialize
    def to_dict(self):
        """Create dictionary representation of the error."""
        d = {"num_errors": self.num_errors, "num_warnings": self.num_warnings}
        if self.errors:
            errors = []
            for error in self.errors:
                errors.append(error.as_dict())
            d["errors"] = errors
        if self.warnings:
            warnings = []
            for warning in self.warnings:
                warnings.append(warning.as_dict())
            d["warnings"] = warnings
        if self.msg:
            d["error_message"] = self.msg

        d["error_code"] = self.ERROR_CODE

        return d

    def as_dict(self):
        """Create dictionary representation of the error."""
        return self.to_dict()

    @classmethod
    def from_dict(cls, d):
        """Create instance of the error from its dictionary representation."""
        dec = MontyDecoder()
        warnings = (
            [dec.process_decoded(w) for w in d["warnings"]] if "warnings" in d else []
        )
        errors = [dec.process_decoded(w) for w in d["errors"]] if "errors" in d else []
        msg = d["error_message"] if "error_message" in d else None

        return cls(
            warnings=warnings,
            errors=errors,
            num_errors=d["num_errors"],
            num_warnings=d["num_warnings"],
            msg=msg,
        )


class UnconvergedError(AbinitRuntimeError):
    """Exception raised when a calculation didn't converge within the selected number of restarts."""

    ERROR_CODE = ErrorCode.UNCONVERGED

    def __init__(
        self,
        job=None,
        msg=None,
        num_errors=None,
        num_warnings=None,
        errors=None,
        warnings=None,
        abinit_input=None,
        restart_info=None,
        history=None,
    ):
        """Construct UnconvergedError object.

        If the job has a report all the information will be extracted from it, otherwise the arguments will be used.
        It contains information that can be used to further restart the job.

        Parameters
        ----------
        job
            the atomate2 job
        msg
            the error message
        num_errors
            number of errors in the abinit execution. Only used if job doesn't have a report.
        num_warnings
            number of warning in the abinit execution. Only used if job doesn't have a report.
        errors
            list of errors in the abinit execution. Only used if job doesn't have a report.
        warnings
            list of warnings in the abinit execution. Only used if job doesn't have a report.
        abinit_input
            the last AbinitInput used.
        restart_info
            the RestartInfo required to restart the job.
        history
            The history of the job.
        """
        super().__init__(job, msg, num_errors, num_warnings, errors, warnings)
        self.abinit_input = abinit_input
        self.restart_info = restart_info
        self.history = history

    @pmg_serialize
    def to_dict(self):
        """Create dictionary representation of the error."""
        d = super().to_dict()
        d["abinit_input"] = self.abinit_input.as_dict() if self.abinit_input else None
        d["restart_info"] = self.restart_info.as_dict() if self.restart_info else None
        d["history"] = self.history.as_dict() if self.history else None
        return d

    @classmethod
    def from_dict(cls, d):
        """Create instance of the error from its dictionary representation."""
        dec = MontyDecoder()
        warnings = (
            [dec.process_decoded(w) for w in d["warnings"]] if "warnings" in d else []
        )
        errors = [dec.process_decoded(w) for w in d["errors"]] if "errors" in d else []
        if "abinit_input" in d and d["abinit_input"] is not None:
            abinit_input = dec.process_decoded(d["abinit_input"])
        else:
            abinit_input = None
        if "restart_info" in d and d["restart_info"] is not None:
            restart_info = dec.process_decoded(d["restart_info"])
        else:
            restart_info = None
        if "history" in d and d["history"] is not None:
            history = dec.process_decoded(d["history"])
        else:
            history = None
        return cls(
            warnings=warnings,
            errors=errors,
            num_errors=d["num_errors"],
            num_warnings=d["num_warnings"],
            msg=d["error_message"],
            abinit_input=abinit_input,
            restart_info=restart_info,
            history=history,
        )


class WalltimeError(AbiAtomateError):
    """Exception raised when the calculation didn't complete within the specified walltime."""

    ERROR_CODE = ErrorCode.WALLTIME


class InitializationError(AbiAtomateError):
    """Exception raised if errors are present during the initialization of the job, before abinit is started."""

    ERROR_CODE = ErrorCode.INITIALIZATION


class RestartError(InitializationError):
    """Exception raised if errors show up during the set up of the restart."""

    ERROR_CODE = ErrorCode.RESTART


class PostProcessError(AbiAtomateError):
    """Exception raised if problems are encountered during the post processing of the abinit calculation."""

    ERROR_CODE = ErrorCode.POSTPROCESS


class RestartInfo(MSONable):
    """Object that contains the information about the restart of a job."""

    def __init__(self, previous_dir, num_restarts=0):
        self.previous_dir = previous_dir
        # self.reset = reset
        self.num_restarts = num_restarts

    @pmg_serialize
    def as_dict(self):
        """Create dictionary representation of the error."""
        return dict(
            previous_dir=self.previous_dir,
            # reset=self.reset,
            num_restarts=self.num_restarts,
        )

    @classmethod
    def from_dict(cls, d):
        """Create instance of the error from its dictionary representation."""
        return cls(
            previous_dir=d["previous_dir"],
            # reset=d["reset"],
            num_restarts=d["num_restarts"],
        )

    @property
    def prev_outdir(self):
        """Get the Directory object pointing to the output directory of the previous step."""
        return Directory(os.path.join(self.previous_dir, OUTDIR_NAME))

    @property
    def prev_indir(self):
        """Get the Directory object pointing to the input directory of the previous step."""
        return Directory(os.path.join(self.previous_dir, INDIR_NAME))
