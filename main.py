from fastapi import FastAPI, UploadFile, File, HTTPException, status, Query
from bs4 import BeautifulSoup
from pydantic import BaseModel
from typing import List
import re

app = FastAPI()

# ------------------------------------------------------------------
# In-memory storage
# ------------------------------------------------------------------
students = {}   # student_id -> {"history": [...], "plan": [...]}
catalog = {}    # normalized_code -> catalog entry dict


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------
class HistoryCourse(BaseModel):
    course_code: str
    term: str
    credits_earned: int
    status: str


class HistoryUpdate(BaseModel):
    history: List[HistoryCourse]


class PlannedCourse(BaseModel):
    course_code: str
    term: str


class PlanUpdate(BaseModel):
    planned_courses: List[PlannedCourse]


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------
SEASON_ORDER = {
    "W": 0,
    "SP": 1,
    "S": 2,
    "F": 3
}


def normalize_code(code: str) -> str:
    """
    Format-insensitive course code matching:
    COSC 3506 = COSC-3506 = cosc3506 -> COSC3506
    """
    return re.sub(r"[\s\-]", "", code).upper()


def parse_term(term: str):
    """
    Parse terms for chronological sorting.
    Example:
    23F -> (23, 3)
    26SP -> (26, 1)
    """
    m = re.match(r"^(\d{2})(W|SP|S|F)$", term.strip().upper())

    if not m:
        return (9999, 9999)

    year = int(m.group(1))
    season = m.group(2)

    return (year, SEASON_ORDER[season])


def term_before(term_a: str, term_b: str) -> bool:
    """
    Returns True if term_a is strictly earlier than term_b.
    """
    return parse_term(term_a) < parse_term(term_b)


def grade_rank(grade: str) -> int:
    """
    Used for transcript deduplication.
    Numeric grade beats letter grade beats P/blank.
    """
    grade = grade.strip()

    if grade.isdigit():
        return 3

    if grade and grade.upper() != "P":
        return 2

    if grade.upper() == "P":
        return 1

    return 0


def parse_credits(text: str) -> int:
    """
    Convert credits text into an integer.
    Blank or non-numeric credits become 0.
    """
    text = text.strip()
    match = re.search(r"\d+", text)

    if match:
        return int(match.group())

    return 0


def normalize_header(text: str) -> str:
    """
    Normalize table headers so matching is easier.
    """
    return text.strip().lower().replace(" ", "")


def check_student_exists(student_id: str):
    if student_id not in students:
        raise HTTPException(status_code=404, detail="Student not found")


# ------------------------------------------------------------------
# Phase 1: Catalog parsing
# ------------------------------------------------------------------
def parse_catalog_html(html_bytes: bytes) -> dict:
    soup = BeautifulSoup(html_bytes, "html.parser")
    table = soup.find("table")

    if not table:
        return {}

    result = {}
    rows = table.find_all("tr")[1:]

    for row in rows:
        cols = row.find_all("td")

        if len(cols) < 4:
            continue

        code = cols[0].get_text(strip=True)
        title = cols[1].get_text(strip=True)
        credits = cols[2].get_text(strip=True)
        prereqs = cols[3].get_text(" ", strip=True)
        cross = cols[4].get_text(" ", strip=True) if len(cols) > 4 else ""

        if prereqs.lower() == "none" or prereqs == "":
            prereq_list = []
        else:
            raw_prereqs = re.findall(r"[A-Z]{2,5}[-\s]?\d{4}", prereqs.upper())
            prereq_list = [normalize_code(c) for c in raw_prereqs]

        if cross.lower() == "none" or cross == "":
            cross_list = []
        else:
            raw_cross = re.findall(r"[A-Z]{2,5}[-\s]?\d{4}", cross.upper())
            cross_list = [normalize_code(c) for c in raw_cross]

        norm_code = normalize_code(code)

        # Canonical readable format, e.g. COSC 3506 -> COSC-3506
        display_code = re.sub(r"\s+", "-", code.strip().upper())

        result[norm_code] = {
            "course_code": display_code,
            "title": title,
            "credits": int(credits) if credits.isdigit() else 0,
            "prerequisites": prereq_list,
            "cross_listed": cross_list
        }

    return result


# ------------------------------------------------------------------
# Phase 2: Transcript parsing
# ------------------------------------------------------------------
def parse_transcript_html(html_text: str):
    soup = BeautifulSoup(html_text, "html.parser")

    valid_statuses = {"Completed", "In-Progress", "Attempted"}
    deduped = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")

        if not rows:
            continue

        header_index = None
        header_map = {}

        for i, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            headers = [
                normalize_header(c.get_text(" ", strip=True))
                for c in cells
            ]

            if (
                "status" in headers
                and "course" in headers
                and "grade" in headers
                and "term" in headers
                and "credits" in headers
            ):
                header_index = i
                header_map = {
                    header: index
                    for index, header in enumerate(headers)
                }
                break

        if header_index is None:
            continue

        for row in rows[header_index + 1:]:
            cells = row.find_all("td")

            if len(cells) < 5:
                continue

            try:
                status_text = cells[header_map["status"]].get_text(" ", strip=True)
                course_text = cells[header_map["course"]].get_text(" ", strip=True)
                grade_text = cells[header_map["grade"]].get_text(" ", strip=True)
                term_text = cells[header_map["term"]].get_text(" ", strip=True)
                credits_text = cells[header_map["credits"]].get_text(" ", strip=True)
            except IndexError:
                continue

            if status_text not in valid_statuses:
                continue

            if not term_text:
                continue

            course_parts = course_text.split()

            if not course_parts:
                continue

            course_code = course_parts[0]
            credits_earned = parse_credits(credits_text)

            key = (normalize_code(course_code), term_text)

            record = {
                "course_code": course_code,
                "term": term_text,
                "credits_earned": credits_earned,
                "status": status_text
            }

            if key not in deduped:
                deduped[key] = {
                    "record": record,
                    "grade": grade_text
                }
            else:
                old = deduped[key]

                better_grade = grade_rank(grade_text) > grade_rank(old["grade"])

                tie_better_credits = (
                    grade_rank(grade_text) == grade_rank(old["grade"])
                    and credits_earned > old["record"]["credits_earned"]
                )

                if better_grade or tie_better_credits:
                    deduped[key] = {
                        "record": record,
                        "grade": grade_text
                    }

    return [item["record"] for item in deduped.values()]


# ------------------------------------------------------------------
# Phase 3: Audit engine
# ------------------------------------------------------------------
def run_audit(student_id: str, strict: bool):
    student = students[student_id]
    history = student["history"]
    plan = student["plan"]

    # History lookup:
    # normalized_code -> list of history records
    history_by_code = {}

    for h in history:
        normalized = normalize_code(h["course_code"])
        history_by_code.setdefault(normalized, []).append(h)

    # Best completed record per course.
    # This prevents double-counting retakes.
    best_completed = {}

    for h in history:
        if h["status"] != "Completed":
            continue

        normalized = normalize_code(h["course_code"])
        current_credits = h["credits_earned"]

        if normalized not in best_completed:
            best_completed[normalized] = h
        else:
            existing = best_completed[normalized]

            # Prefer higher credits first.
            # If credits tie, prefer the later completed term.
            if current_credits > existing["credits_earned"]:
                best_completed[normalized] = h
            elif current_credits == existing["credits_earned"]:
                if parse_term(h["term"]) > parse_term(existing["term"]):
                    best_completed[normalized] = h

    # Important change:
    # Cross-list conflict checks completed courses.
    # The assignment says completed, not only completed-with-credits.
    completed_codes = set(best_completed.keys())

    # --------------------------------------------------------------
    # Missing prerequisite detection
    # --------------------------------------------------------------
    term_errors = {}

    for planned in plan:
        planned_norm = normalize_code(planned["course_code"])
        planned_term = planned["term"]

        catalog_entry = catalog.get(planned_norm)

        if catalog_entry is None:
            continue

        for prereq_norm in catalog_entry["prerequisites"]:
            prereq_records = history_by_code.get(prereq_norm, [])

            satisfied = any(
                record["status"] == "Completed"
                and term_before(record["term"], planned_term)
                for record in prereq_records
            )

            if not satisfied:
                prereq_display = catalog.get(prereq_norm, {}).get(
                    "course_code",
                    prereq_norm
                )

                term_errors.setdefault(planned_term, []).append({
                    "course_code": planned["course_code"],
                    "type": "MISSING_PREREQUISITE",
                    "message": f"Missing prerequisite: {prereq_display}"
                })

    sorted_terms = sorted(term_errors.keys(), key=parse_term)

    timeline_validation = [
        {
            "term": term,
            "errors": term_errors[term]
        }
        for term in sorted_terms
    ]

    # --------------------------------------------------------------
    # Cross-list violations
    # --------------------------------------------------------------
    cross_list_violations = []

    for planned in plan:
        planned_norm = normalize_code(planned["course_code"])
        catalog_entry = catalog.get(planned_norm)

        if catalog_entry is None:
            continue

        for cross_norm in catalog_entry["cross_listed"]:
            if cross_norm in completed_codes:
                cross_display = catalog.get(cross_norm, {}).get(
                    "course_code",
                    cross_norm
                )

                cross_list_violations.append({
                    "course_code": planned["course_code"],
                    "type": "CROSS_LIST_CONFLICT",
                    "message": f"Cross-listed with completed course {cross_display}"
                })

    # --------------------------------------------------------------
    # Credit summary
    # --------------------------------------------------------------
    total_earned = sum(
        record["credits_earned"]
        for record in best_completed.values()
    )

    total_planned = 0

    for planned in plan:
        planned_norm = normalize_code(planned["course_code"])
        catalog_entry = catalog.get(planned_norm)

        if catalog_entry:
            total_planned += catalog_entry["credits"]

    total_remaining = max(0, 120 - total_earned - total_planned)

    # --------------------------------------------------------------
    # Status
    # --------------------------------------------------------------
    has_issues = bool(timeline_validation or cross_list_violations)

    if has_issues and strict:
        audit_status = "failed"
    elif has_issues:
        audit_status = "warning"
    else:
        audit_status = "ok"

    return {
        "student_id": student_id,
        "status": audit_status,
        "timeline_validation": timeline_validation,
        "cross_list_violations": cross_list_violations,
        "credit_summary": {
            "total_earned": total_earned,
            "total_planned": total_planned,
            "total_remaining_for_graduation": total_remaining
        }
    }


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@app.get("/")
def home():
    return {"message": "Academic Audit API is running"}


# ------------------------------------------------------------------
# Phase 1: Catalog endpoints
# ------------------------------------------------------------------
@app.post("/api/v1/admin/catalog/import", status_code=201)
async def import_catalog(file: UploadFile = File(...)):
    content = await file.read()
    parsed = parse_catalog_html(content)

    catalog.clear()
    catalog.update(parsed)

    return {
        "message": f"Successfully imported {len(parsed)} courses"
    }


@app.get("/api/v1/catalog/courses/{course_code}")
def get_course(course_code: str):
    norm = normalize_code(course_code)

    if norm not in catalog:
        raise HTTPException(
            status_code=404,
            detail=f"Course {course_code} not found"
        )

    return catalog[norm]


# ------------------------------------------------------------------
# Phase 2: History endpoints
# ------------------------------------------------------------------
@app.post(
    "/api/v1/students/{student_id}/history/import",
    status_code=status.HTTP_201_CREATED
)
async def import_history(student_id: str, file: UploadFile = File(...)):
    content = await file.read()

    try:
        html_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File must be valid HTML"
        )

    history = parse_transcript_html(html_text)

    students[student_id] = {
        "history": history,
        "plan": []
    }

    return {
        "status": "success",
        "past_courses_imported": len(history)
    }


@app.put("/api/v1/students/{student_id}/history")
def update_history(student_id: str, body: HistoryUpdate):
    check_student_exists(student_id)

    students[student_id]["history"] = [
        course.model_dump() for course in body.history
    ]

    return {
        "status": "success",
        "message": "Academic history updated successfully"
    }


@app.delete("/api/v1/students/{student_id}/history")
def delete_history(student_id: str):
    check_student_exists(student_id)

    students[student_id]["history"] = []

    return {
        "status": "success",
        "message": "Academic history cleared successfully"
    }


# ------------------------------------------------------------------
# Phase 2: Plan endpoints
# ------------------------------------------------------------------
@app.post("/api/v1/students/{student_id}/plan")
def create_plan(student_id: str, body: PlanUpdate):
    check_student_exists(student_id)

    students[student_id]["plan"] = [
        course.model_dump() for course in body.planned_courses
    ]

    return {
        "status": "success",
        "planned_courses_saved": len(body.planned_courses)
    }


@app.put("/api/v1/students/{student_id}/plan")
def update_plan(student_id: str, body: PlanUpdate):
    check_student_exists(student_id)

    students[student_id]["plan"] = [
        course.model_dump() for course in body.planned_courses
    ]

    return {
        "status": "success",
        "planned_courses_saved": len(body.planned_courses)
    }


@app.delete("/api/v1/students/{student_id}/plan")
def delete_plan(student_id: str):
    check_student_exists(student_id)

    students[student_id]["plan"] = []

    return {
        "status": "success",
        "message": "Plan cleared successfully"
    }


# ------------------------------------------------------------------
# Phase 2: Profile endpoint
# ------------------------------------------------------------------
@app.get("/api/v1/students/{student_id}/profile")
def get_profile(student_id: str):
    check_student_exists(student_id)

    return {
        "student_id": student_id,
        "history": students[student_id]["history"],
        "plan": students[student_id]["plan"]
    }


# ------------------------------------------------------------------
# Phase 3: Audit report endpoint
# ------------------------------------------------------------------
@app.get("/api/v1/students/{student_id}/audit-report")
def get_audit_report(
    student_id: str,
    strict: bool = Query(default=False)
):
    check_student_exists(student_id)

    return run_audit(student_id, strict)