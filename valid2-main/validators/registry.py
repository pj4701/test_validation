from .actuals_validator import run_validation as run_actuals
from .uom_validator import run_validation as run_uom
from .asp_past_validator import run_validation as run_asp_past
from .asp_override_validator import run_validation as run_asp_override


VALIDATIONS = {
    "Actuals Validation": {
        "runner": run_actuals,
        "files": [
            "Sales File", "Item File", "UOM File", "Target File"
        ],
        "description": "Source sales vs o9 Actual Raw reconciliation.",
    },
    "UOM Conversion Validation": {
        "runner": run_uom,
        "files": [
            "UOM Source File", "Item File", "UOM Target File"
        ],
        "description": "UOM conversion master reconciliation.",
    },
    "o9 Compare Past ASP": {
        "runner": run_asp_past,
        "files": [
            "ASP Source File", "ASP Past Target File"
        ],
        "description": "Past-month ASP and revenue reconciliation.",
    },
    "ASP Override Current & Future": {
        "runner": run_asp_override,
        "files": [
            "ASP Override Source File",
            "ASP Current Future Target File",
            "Demand Domain Mapping File",
            "ASP Rejection File",
        ],
        "description": "Current/future ASP override reconciliation with rejection analysis.",
    },
}
