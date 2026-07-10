import requests

BASE = "https://academic-audit-api.onrender.com"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*"
}

with open("sample_catalog.html", "rb") as f:
    r = requests.post(
        f"{BASE}/api/v1/admin/catalog/import",
        files={"file": ("sample_catalog.html", f, "text/html")},
        headers=headers
    )

print("STATUS:", r.status_code)
print("FIRST 500 CHARS:")
print(r.text[:500])
