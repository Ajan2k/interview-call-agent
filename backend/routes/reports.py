from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from services.report_service import ReportService
from services.database_manager import CallRepository, DatabaseManager

router = APIRouter(prefix="/report", tags=["Reports"])

# Class-based service instance
_db_manager = DatabaseManager()
_call_repo = CallRepository(_db_manager)
_report_service = ReportService(call_repo=_call_repo)


@router.get("")
def get_report(
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    direction: str = Query(""),
    lead_status: str = Query("", alias="lead"),
    language: str = Query(""),
):
    """Customizable report: filtered calls plus summary counts for dashboard."""
    return _report_service.generate_report(
        date_from=date_from,
        date_to=date_to,
        direction=direction,
        lead_status=lead_status,
        language=language,
    )


@router.get("/export")
def export_report_csv(
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    direction: str = Query(""),
    lead_status: str = Query("", alias="lead"),
    language: str = Query(""),
):
    """Download the filtered report as a CSV file."""
    csv_content = _report_service.generate_csv(
        date_from=date_from,
        date_to=date_to,
        direction=direction,
        lead_status=lead_status,
        language=language,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=call_report.csv"},
    )
