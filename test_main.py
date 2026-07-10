def test_home_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "Academic Audit API is running" in response.json()["message"]


def test_missing_course_returns_404():
    response = client.get("/api/v1/catalog/courses/FAKE9999")
    assert response.status_code == 404


def test_missing_student_profile_returns_404():
    response = client.get("/api/v1/students/doesnotexist/profile")
    assert response.status_code == 404


def test_delete_missing_student_history_returns_404():
    response = client.delete("/api/v1/students/doesnotexist/history")
    assert response.status_code == 404


def test_delete_missing_student_plan_returns_404():
    response = client.delete("/api/v1/students/doesnotexist/plan")
    assert response.status_code == 404


def test_catalog_course_lookup_format_insensitive():
    html = """
    <html>
    <body>
    <table>
        <tr>
            <th>Course Code</th>
            <th>Title</th>
            <th>Credits</th>
            <th>Prerequisites</th>
            <th>Cross-listed</th>
        </tr>
        <tr>
            <td>COSC 3506</td>
            <td>Software Systems Development</td>
            <td>3</td>
            <td>COSC 2007</td>
            <td>ITEC 3506</td>
        </tr>
    </table>
    </body>
    </html>
    """

    response = client.post(
        "/api/v1/admin/catalog/import",
        files={"file": ("catalog.html", html, "text/html")}
    )

    assert response.status_code == 201

    response = client.get("/api/v1/catalog/courses/COSC-3506")
    assert response.status_code == 200
    assert response.json()["credits"] == 3
    assert "COSC2007" in response.json()["prerequisites"]
    assert "ITEC3506" in response.json()["cross_listed"]


def test_update_and_delete_history_and_plan():
    student_id = "999"

    history_body = {
        "history": [
            {
                "course_code": "COSC-2007",
                "term": "24F",
                "credits_earned": 3,
                "status": "Completed"
            }
        ]
    }

    # Create student first using history import
    html = """
    <html>
    <body>
    <table>
        <tr>
            <th>Status</th>
            <th>Course</th>
            <th>Grade</th>
            <th>Term</th>
            <th>Credits</th>
        </tr>
        <tr>
            <td>Completed</td>
            <td>COSC-2006</td>
            <td>80</td>
            <td>24W</td>
            <td>3</td>
        </tr>
    </table>
    </body>
    </html>
    """

    response = client.post(
        f"/api/v1/students/{student_id}/history/import",
        files={"file": ("student.html", html, "text/html")}
    )
    assert response.status_code == 201

    response = client.put(
        f"/api/v1/students/{student_id}/history",
        json=history_body
    )
    assert response.status_code == 200

    plan_body = {
        "planned_courses": [
            {
                "course_code": "COSC-3506",
                "term": "26F"
            }
        ]
    }

    response = client.post(
        f"/api/v1/students/{student_id}/plan",
        json=plan_body
    )
    assert response.status_code == 200

    response = client.get(f"/api/v1/students/{student_id}/profile")
    assert response.status_code == 200
    assert response.json()["history"][0]["course_code"] == "COSC-2007"
    assert response.json()["plan"][0]["course_code"] == "COSC-3506"

    response = client.delete(f"/api/v1/students/{student_id}/plan")
    assert response.status_code == 200

    response = client.delete(f"/api/v1/students/{student_id}/history")
    assert response.status_code == 200