"""
Lab 11 — Helper Utilities
"""
import asyncio

from google.genai import types


def extract_text(content) -> str:
    """Extract plain text from a types.Content (or any object with .parts).

    Shared by input/output guardrail plugins and event handling.
    """
    text = ""
    if content and getattr(content, "parts", None):
        for part in content.parts:
            if getattr(part, "text", None):
                text += part.text
    return text


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc)
    return "RESOURCE_EXHAUSTED" in msg or "429" in msg


async def chat_with_agent(agent, runner, user_message: str, session_id=None,
                          max_retries: int = 3):
    """Send a message to the agent and get the response.

    Retries automatically with backoff when the free-tier rate limit (429)
    is hit, so a burst of requests degrades to waiting instead of crashing.

    Args:
        agent: The LlmAgent instance
        runner: The InMemoryRunner instance
        user_message: Plain text message to send
        session_id: Optional session ID to continue a conversation
        max_retries: Attempts before giving up on rate-limit errors

    Returns:
        Tuple of (response_text, session)
    """
    user_id = "student"
    app_name = runner.app_name

    session = None
    if session_id is not None:
        try:
            session = await runner.session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
        except (ValueError, KeyError):
            pass

    if session is None:
        session = await runner.session_service.create_session(
            app_name=app_name, user_id=user_id
        )

    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)],
    )

    for attempt in range(1, max_retries + 1):
        try:
            final_response = ""
            async for event in runner.run_async(
                user_id=user_id, session_id=session.id, new_message=content
            ):
                if getattr(event, "content", None):
                    final_response += extract_text(event.content)
            return final_response, session
        except Exception as e:
            if _is_rate_limit_error(e) and attempt < max_retries:
                wait = 20 * attempt
                print(f"  (rate-limited, retrying in {wait}s — "
                      f"attempt {attempt}/{max_retries})")
                await asyncio.sleep(wait)
            else:
                raise
