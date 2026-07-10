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
    r = client.delete("/api/v1/students/111/plan