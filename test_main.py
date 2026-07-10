from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_home():
    r = client.get("/")
    assert r.status_code == 200


def test_import_catalog():
    with open("sample_catalog.html", "rb") as f:
        r = client.post("/api/v1/admin/catalog/import",
                        files={"file": ("catalog.html", f, "text/html")})
    assert r.status_code == 201


def test_get_course():
    r = client.get("/api/v1/catalog/courses/COSC3506")
    assert r.status_code == 200


def test_get_course_not_found():
    r = client.get("/api/v1/catalog/courses/FAKE9999")
    assert r.status_code == 404


def test_import_history():
    with open("student-example.html", "rb") as f:
        r = client.post("/api/v1/students/111/history/import",
                        files={"file": ("t.html", f, "text/html")})
    assert r.status_code == 201
    assert r.json()["past_courses_imported"] == 33


def test_profile():
    r = client.get("/api/v1/students/111/profile")
    assert r.status_code == 200
    data = r.json()
    assert "student_id" in data
    assert "history" in data
    assert "plan" in data


def test_404_unknown_student():
    r = client.get("/api/v1/students/999/profile")
    assert r.status_code == 404


def test_plan_post():
    r = client.post("/api/v1/students/111/plan",
                    json={"planned_courses": [
                        {"course_code": "ITEC-3506", "term": "26F"}
                    ]})
    assert r.status_code == 200
    assert r.json()["planned_courses_saved"] == 1


def test_plan_put():
    r = client.put("/api/v1/students/111/plan",
                   json={"planned_courses": [
                       {"course_code": "COSC-3506", "term": "26F"}
                   ]})
    assert r.status_code == 200


def test_plan_delete():
    r = client.delete("/api/v1/students/111/plan")
    assert r.status_code == 200


def test_history_put():
    r = client.put("/api/v1/students/111/history",
                   json={"history": [
                       {"course_code": "COSC-1046", "term": "23F",
                        "credits_earned": 3, "status": "Completed"}
                   ]})
    assert r.status_code == 200


def test_history_delete():
    r = client.delete("/api/v1/students/111/history")
    assert r.status_code == 200


def test_audit_report():
    with open("student-example.html", "rb") as f:
        client.post("/api/v1/students/111/history/import",
                    files={"file": ("t.html", f, "text/html")})
    r = client.get("/api/v1/students/111/audit-report")
    assert r.status_code == 200
    data = r.json()
    assert "student_id" in data
    assert "status" in data
    assert "timeline_validation" in data
    assert "cross_list_violations" in data
    assert "credit_summary" in data


def test_audit_strict_true():
    r = client.get("/api/v1/students/111/audit-report?strict=true")
    assert r.status_code == 200
    assert r.json()["status"] in ["ok", "failed", "warning"]


def test_audit_404():
    r = client.get("/api/v1/students/999/audit-report")
    assert r.status_code == 404


def test_plan_404():
    r = client.post("/api/v1/students/999/plan",
                    json={"planned_courses": []})
    assert r.status_code == 404


def test_history_put_404():
    r = client.put("/api/v1/students/999/history",
                   json={"history": []})
    assert r.status_code == 404


def test_history_delete_404():
    r = client.delete("/api/v1/students/999/history")
    assert r.status_code == 404


def test_plan_delete_404():
    r = client.delete("/api/v1/students/999/plan")
    assert r.status_code == 404