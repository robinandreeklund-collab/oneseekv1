import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import config
from app.routes.new_llm_config_routes import router as llm_config_router
from app.routes.public_global_chat_routes import (
    get_public_agent,
    get_public_chat_rate_limiter,
    router as public_global_router,
)
from app.services.anonymous_session_service import ANON_SESSION_COOKIE_NAME
from app.users import current_optional_user


class FakeChunk:
    def __init__(self, content: str):
        self.content = content


class FakeAgent:
    async def astream_events(self, input_state, config=None, version=None):
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": FakeChunk("Hello")},
        }
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": FakeChunk(" world")},
        }


def build_app():
    app = FastAPI()
    app.include_router(public_global_router, prefix="/api/v1")
    app.include_router(llm_config_router, prefix="/api/v1")
    app.dependency_overrides[get_public_agent] = lambda: (
        FakeAgent(),
        None,
        0,
        ["search_web"],
    )
    app.dependency_overrides[current_optional_user] = lambda: None
    return app


def test_public_global_chat_anonymous_sets_cookie():
    config.ANON_ACCESS_ENABLED = True
    limiter = get_public_chat_rate_limiter()
    limiter.clear()

    app = build_app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/public/global/chat",
        json={"user_query": "Hello"},
    )

    assert response.status_code == 200
    assert response.headers.get("x-vercel-ai-ui-message-stream") == "v1"
    assert ANON_SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")
    assert "data: [DONE]" in response.text


def test_public_global_chat_logged_in_does_not_set_cookie():
    config.ANON_ACCESS_ENABLED = True
    limiter = get_public_chat_rate_limiter()
    limiter.clear()

    app = build_app()
    user = SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[current_optional_user] = lambda: user
    client = TestClient(app)

    response = client.post(
        "/api/v1/public/global/chat",
        json={"user_query": "Hello"},
    )

    assert response.status_code == 200
    assert ANON_SESSION_COOKIE_NAME not in response.headers.get("set-cookie", "")


def test_global_llm_configs_public():
    config.GLOBAL_LLM_CONFIGS = []
    app = build_app()
    client = TestClient(app)

    response = client.get("/api/v1/global-new-llm-configs")

    assert response.status_code == 200
    assert response.json() == []
