from fastapi.testclient import TestClient

from app.schemas import HelloWorldResponse


def test_hello_world(client: TestClient) -> None:
    response = client.get("/hello-world")
    assert response.status_code == 200
    assert HelloWorldResponse.model_validate(response.json()).message == "Hello, world!"
    assert response.json() == {"message": "Hello, world!"}


def test_openapi_schema_documents_response(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    ref = schema["paths"]["/hello-world"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert ref.endswith("/HelloWorldResponse")
