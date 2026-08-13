"""Domain exceptions used to fail safely and explain pipeline errors."""

class PipelineError(Exception):
    """Base class for controlled ETL failures."""

class MissingColumnError(PipelineError):
    """Raised when the source structure omits mandatory columns."""

class InvalidDateError(PipelineError):
    """Raised for invalid date configuration or master values."""

class MasterDataError(PipelineError):
    """Raised when persisted master data is corrupt or unreadable."""

class DuplicateBusinessKeyError(PipelineError):
    """Raised when a configured business key is not unique."""

class DataValidationError(PipelineError):
    """Raised when final data integrity validation fails."""

