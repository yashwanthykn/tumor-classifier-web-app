import os
import re
import json
import logging
from typing import AsyncIterator, Dict, List, Any, Optional

from sqlalchemy.orm import Session
from groq import Groq

from app.crud import prediction as crud_prediction
from app.crud import conversation as crud_conversation
from app.database.models import Message, MessageRole

# Setup logger
logger = logging.getLogger(__name__)


class ChatAgent:
    def __init__(
        self,
        user_id: int,
        conversation_id: str,
        db: Session,
        api_key: Optional[str] = None,
    ):
        """Initialize the chat agent with Groq and load history from DB."""
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.db = db

        # Initialize Groq client
        self.client = Groq(api_key=api_key or os.getenv("GROQ_API_KEY"))

        self.conversation_history: List[Dict[str, Any]] = []
        self.max_tokens = 2048
        self.model = "llama-3.3-70b-versatile"

        # Load existing conversation history from DB
        self._load_history_from_db()

        logger.info(
            f"ChatAgent initialized for user={self.user_id}, "
            f"conversation={conversation_id}, "
            f"loaded {len(self.conversation_history)} history messages"
        )

    def _load_history_from_db(self) -> None:
        """Load previous messages from the database into conversation_history."""
        messages = crud_conversation.get_conversation_messages(
            self.db,
            conversation_id=self.conversation_id,
            user_id=self.user_id,
        )

        for msg in messages:
            if msg.role == MessageRole.tool:
                entry = {
                    "role": "tool",
                    "tool_call_id": msg.tool_name or "",
                    "content": msg.content,
                }
            elif msg.role == MessageRole.assistant and msg.tool_name:
                tool_calls = []
                if msg.tool_input:
                    try:
                        tool_calls = json.loads(msg.tool_input)
                    except (json.JSONDecodeError, TypeError):
                        pass

                entry = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": tool_calls,
                }
            else:
                entry = {
                    "role": (
                        msg.role.value
                        if isinstance(msg.role, MessageRole)
                        else msg.role
                    ),
                    "content": msg.content,
                }

            self.conversation_history.append(entry)

    def get_system_prompt(self) -> str:
        return """You are an AI medical assistant for a brain tumor classification application.

**YOUR ROLE:**
You help users understand their MRI scan results and provide educational information about brain tumors.

**YOUR CAPABILITIES:**
- Explain brain tumor types (glioblastoma, meningioma, pituitary tumors, etc.)
- Interpret MRI scan predictions with confidence scores
- Access user's scan history using the get_user_predictions tool
- Provide information about tumor stages and characteristics
- Answer questions about symptoms, diagnosis, and general medical information

**CRITICAL SAFETY RULES:**
1. You are NOT a replacement for medical professionals
2. Always recommend consulting a doctor for medical advice
3. Never make definitive diagnoses or treatment recommendations
4. Be empathetic but factual - balance compassion with accuracy
5. If symptoms seem urgent, strongly recommend immediate medical attention

**WHEN TO USE TOOLS:**
- User asks about "my scans" or "my history" → use get_user_predictions
- User asks about statistics or patterns → use get_user_statistics
- User asks general medical questions → answer from your knowledge, no tool needed

**TONE:**
- Professional but warm
- Educational and informative
- Empathetic when discussing concerning results
- Clear and jargon-free (explain medical terms)

**RESPONSE FORMAT:**
- Keep responses concise (2-4 paragraphs max)
- Use bullet points for multiple items
- Always end with "Is there anything specific you'd like to know more about?"

Remember: Education and support, not diagnosis or treatment advice."""

    def get_tools(self) -> List[Dict[str, Any]]:
        """Define tools in OpenAI format (Groq compatible)"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_user_predictions",
                    "description": "Retrieves the user's MRI scan prediction history from the database. Use when user asks about their scans, results, or history.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of recent predictions to return (default: 10, max: 50)",
                                "default": 10,
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_user_statistics",
                    "description": "Gets aggregated statistics about user's scan history including total scans, tumors detected, and average confidence.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ]

    def _parse_inline_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse tool calls embedded in text content by Llama.

        Llama 3.3 sometimes outputs tool calls as raw text instead of using
        the structured tool_calls field. Format:
            <function=tool_name>{"arg": "value"}</function>
        """
        pattern = r"<function=(\w+)>(.*?)</function>"
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            return None

        tool_name = match.group(1)
        try:
            tool_args = json.loads(match.group(2))
        except (json.JSONDecodeError, TypeError):
            tool_args = {}

        preamble = text[: match.start()].strip()

        logger.info(f"Parsed inline tool call: {tool_name}({tool_args})")
        return {
            "name": tool_name,
            "arguments": tool_args,
            "preamble": preamble,
        }

    async def execute_tool(
        self, tool_name: str, tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the requested tool"""
        logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

        try:
            if tool_name == "get_user_predictions":
                limit = tool_input.get("limit", 10)
                limit = min(limit, 50)

                predictions = crud_prediction.get_user_predictions(
                    self.db, user_id=self.user_id, limit=limit
                )

                formatted_predictions = [
                    {
                        "id": pred.id,
                        "date": pred.created_at.isoformat(),
                        "result": pred.prediction_label,
                        "confidence": round(pred.confidence_score, 4),
                        "confidence_percent": f"{pred.confidence_score * 100:.2f}%",
                        "filename": pred.filename,
                    }
                    for pred in predictions
                ]
                return {
                    "success": True,
                    "total_retrieved": len(formatted_predictions),
                    "predictions": formatted_predictions,
                }

            elif tool_name == "get_user_statistics":
                stats = crud_prediction.get_statistics(self.db, user_id=self.user_id)
                return {"success": True, "statistics": stats}
            else:
                logger.error(f"Unknown tool requested: {tool_name}")
                return {"success": False, "error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.exception(f"Tool execution failed: {tool_name}")
            return {"success": False, "error": f"Tool execution failed: {str(e)}"}

    def _call_groq(self, use_tools: bool = True):
        """Make a single Groq API call. Returns the message object."""
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.get_system_prompt()},
                *self.conversation_history[-20:],  # Limit history to save tokens
            ],
            "max_tokens": self.max_tokens,
            "temperature": 0.7,
        }
        if use_tools:
            kwargs["tools"] = self.get_tools()

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message

    async def send_message(self, user_message: str) -> AsyncIterator[str]:
        """Send message and get response.

        Handles the full agentic loop: LLM call → tool execution → LLM call with results.
        Only yields the FINAL text response — never intermediate preambles.
        Tool-call messages are persisted to DB inside the loop.
        """
        # Add user message to in-memory history
        self.conversation_history.append({"role": "user", "content": user_message})

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Agent iteration {iteration}")

            try:
                message = self._call_groq(use_tools=True)

                # ── Path A: Structured tool calls (proper Groq format) ───
                if message.tool_calls:
                    logger.info("AI requested tool use (structured)")

                    tool_calls_list = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ]

                    # Add to history
                    self.conversation_history.append(
                        {
                            "role": "assistant",
                            "content": message.content or "",
                            "tool_calls": tool_calls_list,
                        }
                    )

                    # Persist tool request to DB
                    crud_conversation.save_message(
                        self.db,
                        conversation_id=self.conversation_id,
                        role=MessageRole.assistant,
                        content=message.content or "",
                        tool_name="__tool_request__",
                        tool_input=tool_calls_list,
                    )

                    # Execute each tool
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_input = json.loads(tool_call.function.arguments)
                        logger.info(f"Tool call: {tool_name}({tool_input})")

                        tool_result = await self.execute_tool(tool_name, tool_input)

                        self.conversation_history.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(tool_result),
                            }
                        )

                        crud_conversation.save_message(
                            self.db,
                            conversation_id=self.conversation_id,
                            role=MessageRole.tool,
                            content=json.dumps(tool_result),
                            tool_name=tool_call.id,
                            tool_input=tool_input,
                            tool_result=tool_result,
                        )

                    # Loop back for LLM to generate response using tool results
                    continue

                # ── Path B: Text response (might contain inline tool call) ─
                text_response = message.content or ""

                # Check for inline tool call in text
                inline_call = self._parse_inline_tool_call(text_response)
                if inline_call:
                    logger.info(f"Detected inline tool call: {inline_call['name']}")

                    tool_result = await self.execute_tool(
                        inline_call["name"], inline_call["arguments"]
                    )

                    synthetic_id = f"inline_{inline_call['name']}_{iteration}"

                    # Add to history (preamble + tool call + result)
                    self.conversation_history.append(
                        {
                            "role": "assistant",
                            "content": inline_call.get("preamble", ""),
                            "tool_calls": [
                                {
                                    "id": synthetic_id,
                                    "type": "function",
                                    "function": {
                                        "name": inline_call["name"],
                                        "arguments": json.dumps(
                                            inline_call["arguments"]
                                        ),
                                    },
                                }
                            ],
                        }
                    )
                    self.conversation_history.append(
                        {
                            "role": "tool",
                            "tool_call_id": synthetic_id,
                            "content": json.dumps(tool_result),
                        }
                    )

                    # Persist to DB
                    crud_conversation.save_message(
                        self.db,
                        conversation_id=self.conversation_id,
                        role=MessageRole.assistant,
                        content=inline_call.get("preamble", ""),
                        tool_name="__tool_request__",
                        tool_input=[
                            {
                                "id": synthetic_id,
                                "type": "function",
                                "function": {
                                    "name": inline_call["name"],
                                    "arguments": json.dumps(inline_call["arguments"]),
                                },
                            }
                        ],
                    )
                    crud_conversation.save_message(
                        self.db,
                        conversation_id=self.conversation_id,
                        role=MessageRole.tool,
                        content=json.dumps(tool_result),
                        tool_name=synthetic_id,
                        tool_input=inline_call["arguments"],
                        tool_result=tool_result,
                    )

                    # Loop back — do NOT yield the preamble
                    continue

                # ── Path C: Final text response (no tool calls) ──────────
                logger.info("AI finished - sending final response")

                self.conversation_history.append(
                    {"role": "assistant", "content": text_response}
                )

                yield text_response
                break

            except Exception as e:
                error_str = str(e)
                logger.exception("Error in agent loop")

                # ── Rate limit error ─────────────────────────────────
                if "rate_limit" in error_str.lower() or "429" in error_str:
                    # Extract wait time if available
                    import re as _re

                    wait_match = _re.search(
                        r"try again in (\d+m[\d.]+s|\d+s)", error_str, _re.IGNORECASE
                    )
                    wait_time = wait_match.group(1) if wait_match else "a few minutes"
                    yield f"__ERROR_RATE_LIMIT__{wait_time}"
                    break

                # ── Tool call failed ─────────────────────────────────
                if "tool_use_failed" in error_str or "400" in error_str:
                    logger.warning("Tool call failed, retrying without tools")
                    try:
                        message = self._call_groq(use_tools=False)
                        text_response = message.content or ""
                        self.conversation_history.append(
                            {"role": "assistant", "content": text_response}
                        )
                        yield text_response
                    except Exception as retry_err:
                        retry_str = str(retry_err)
                        if "rate_limit" in retry_str.lower() or "429" in retry_str:
                            wait_match = _re.search(
                                r"try again in (\d+m[\d.]+s|\d+s)",
                                retry_str,
                                _re.IGNORECASE,
                            )
                            wait_time = (
                                wait_match.group(1) if wait_match else "a few minutes"
                            )
                            yield f"__ERROR_RATE_LIMIT__{wait_time}"
                        else:
                            logger.exception("Retry without tools also failed")
                            yield "__ERROR_SERVER__"
                    break

                # ── Connection / timeout errors ──────────────────────
                if "timeout" in error_str.lower() or "connect" in error_str.lower():
                    yield "__ERROR_TIMEOUT__"
                    break

                # ── Generic error ────────────────────────────────────
                yield "__ERROR_SERVER__"
                break

        if iteration >= max_iterations:
            logger.error("Agent hit max iterations")
            yield "__ERROR_MAX_ITERATIONS__"

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        logger.info(f"Cleared conversation history for user={self.user_id}")

    def get_history(self) -> List[Dict[str, str]]:
        """Get current conversation history"""
        return self.conversation_history.copy()

    def set_history(self, history: List[Dict[str, str]]):
        """Set conversation history"""
        self.conversation_history = history
        logger.info(f"Loaded {len(history)} messages into conversation")
