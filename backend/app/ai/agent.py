import os
import re
import json
import time
import logging
from typing import AsyncIterator, Dict, List, Any, Optional

from sqlalchemy.orm import Session
from groq import Groq

from app.crud import prediction as crud_prediction
from app.crud import conversation as crud_conversation
from app.database.models import Message, MessageRole

# Setup logger
logger = logging.getLogger(__name__)

# ── Retry configuration ──────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds — doubles each attempt (1s, 2s, 4s)
RETRYABLE_STATUS_CODES = {"429", "500", "502", "503", "504"}

# ── Context window configuration ─────────────────────────────────────
# Llama 3.3 70B on Groq has a 128K context window, but we use a
# conservative budget to leave room for the response + tool definitions.
# Token estimation: ~4 characters per token for English text.
CHARS_PER_TOKEN = 4
MAX_CONTEXT_TOKENS = 6000  # conservative budget for input messages
SYSTEM_PROMPT_BUDGET = 1500  # reserved for system prompt
TOOL_DEFS_BUDGET = 500  # approximate tokens for tool JSON definitions


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
- Explain a specific scan result in clinical context using the explain_prediction tool
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
- User mentions a specific scan number like "scan #5" or "scan 1" → call explain_prediction directly with prediction_id=5 (or whatever number they said)
- User asks to "explain my last scan" without a number → FIRST call get_user_predictions with limit=1 to find the ID, THEN call explain_prediction with that ID
- User asks general medical questions → answer from your knowledge, no tool needed

**TOOL USAGE RULES:**
- If the user gives you a scan number/ID, call explain_prediction DIRECTLY with that ID. Do NOT call get_user_predictions first — you already have the ID.
- If the user says "my last scan" or "my most recent scan" (no number), FIRST call get_user_predictions with limit=1 to get the ID, THEN call explain_prediction.
- You may chain tool calls across loop iterations. Do NOT try to explain a scan without first fetching the data.

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
            {
                "type": "function",
                "function": {
                    "name": "explain_prediction",
                    "description": "Retrieves a specific MRI scan prediction by ID and returns detailed clinical context for explanation. Use when user asks to explain or interpret a specific scan result.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prediction_id": {
                                "type": "integer",
                                "description": "The ID of the prediction to explain",
                            }
                        },
                        "required": ["prediction_id"],
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

            elif tool_name == "explain_prediction":
                prediction_id = tool_input.get("prediction_id")
                if prediction_id is None:
                    return {
                        "success": False,
                        "error": "prediction_id is required",
                    }

                pred = crud_prediction.get_prediction_by_id(self.db, prediction_id)

                # Authorization: ensure the prediction belongs to this user
                if pred is None or pred.user_id != self.user_id:
                    return {
                        "success": False,
                        "error": f"Prediction #{prediction_id} not found in your history.",
                    }

                # Build rich context for the LLM to explain
                clinical_context = self._build_clinical_context(pred)
                return {
                    "success": True,
                    "prediction": {
                        "id": pred.id,
                        "date": pred.created_at.isoformat(),
                        "filename": pred.filename,
                        "result": pred.prediction_label,
                        "confidence": round(pred.confidence_score, 4),
                        "confidence_percent": f"{pred.confidence_score * 100:.2f}%",
                        "processing_time_ms": round(
                            (pred.processing_time or 0) * 1000, 1
                        ),
                        "model_version": pred.model_version,
                    },
                    "clinical_context": clinical_context,
                }

            else:
                logger.error(f"Unknown tool requested: {tool_name}")
                return {"success": False, "error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.exception(f"Tool execution failed: {tool_name}")
            return {"success": False, "error": f"Tool execution failed: {str(e)}"}

    @staticmethod
    def _build_clinical_context(pred) -> Dict[str, Any]:
        """Build clinical context dict for a prediction to help the LLM explain it.

        This is NOT a diagnosis — it's educational reference material the LLM
        uses to craft a helpful, medically-grounded explanation.
        """
        label = (pred.prediction_label or "").lower()
        confidence = pred.confidence_score or 0.0

        tumor_info = {
            "glioma": {
                "full_name": "Glioma",
                "category": "Primary brain tumor (arises from glial cells)",
                "prevalence": "~33% of all brain tumors, ~80% of malignant brain tumors",
                "typical_characteristics": [
                    "Originates from glial cells (astrocytes, oligodendrocytes, ependymal cells)",
                    "Graded I-IV by WHO; Grade IV = glioblastoma (most aggressive)",
                    "Common symptoms: headaches, seizures, cognitive changes",
                    "MRI typically shows irregular borders, possible contrast enhancement",
                ],
                "important_note": "Grading and treatment planning require biopsy and full clinical workup.",
            },
            "meningioma": {
                "full_name": "Meningioma",
                "category": "Extra-axial tumor (arises from meninges)",
                "prevalence": "~37% of all primary brain tumors; most common primary brain tumor",
                "typical_characteristics": [
                    "Arises from arachnoid cap cells in the meninges",
                    "Usually benign (WHO Grade I in ~80% of cases)",
                    "Typically well-defined, dura-attached, homogeneously enhancing on MRI",
                    "May be asymptomatic and found incidentally",
                ],
                "important_note": "Most meningiomas are slow-growing and benign, but location and size determine clinical significance.",
            },
            "pituitary": {
                "full_name": "Pituitary Adenoma",
                "category": "Sellar/parasellar tumor (arises from pituitary gland)",
                "prevalence": "~17% of all primary brain tumors",
                "typical_characteristics": [
                    "Arises from the anterior pituitary gland",
                    "Classified as functioning (hormone-secreting) or non-functioning",
                    "Microadenoma (<10mm) vs macroadenoma (≥10mm)",
                    "May cause visual field defects (bitemporal hemianopia) if compressing optic chiasm",
                ],
                "important_note": "Often treatable with medication, surgery, or observation depending on type and size.",
            },
            "no tumor": {
                "full_name": "No Tumor Detected",
                "category": "Normal classification",
                "prevalence": "N/A",
                "typical_characteristics": [
                    "The model did not detect patterns consistent with glioma, meningioma, or pituitary tumors",
                    "This is a classification result, not a definitive clinical diagnosis",
                ],
                "important_note": "A 'no tumor' classification does not rule out all pathology. Clinical correlation and professional review are essential.",
            },
        }

        info = tumor_info.get("no tumor")
        for key in tumor_info:
            if key in label:
                info = tumor_info[key]
                break

        if confidence >= 0.95:
            confidence_interpretation = "Very high confidence — the model is highly certain about this classification."
        elif confidence >= 0.80:
            confidence_interpretation = "High confidence — the model is fairly certain, but professional verification is recommended."
        elif confidence >= 0.60:
            confidence_interpretation = "Moderate confidence — there is meaningful uncertainty; clinical review is especially important."
        else:
            confidence_interpretation = "Low confidence — the model is uncertain. This result should be interpreted with significant caution."

        return {
            "tumor_info": info,
            "confidence_interpretation": confidence_interpretation,
            "disclaimer": "This is an AI classification for educational/demonstration purposes only. It is NOT a medical diagnosis. Always consult a qualified healthcare professional.",
        }

    # ══════════════════════════════════════════════════════════════
    #  CONTEXT WINDOW MANAGEMENT
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count from text. ~4 chars per token for English."""
        if not text:
            return 0
        return max(1, len(text) // CHARS_PER_TOKEN)

    @staticmethod
    def _message_tokens(msg: Dict[str, Any]) -> int:
        """Estimate tokens for a single message dict (content + tool data)."""
        tokens = 4  # overhead per message (role, formatting)
        content = msg.get("content", "")
        if content:
            tokens += ChatAgent._estimate_tokens(content)
        if msg.get("tool_calls"):
            tokens += ChatAgent._estimate_tokens(json.dumps(msg["tool_calls"]))
        return tokens

    def _build_context_messages(self) -> List[Dict[str, Any]]:
        """Build a token-aware slice of conversation history for the LLM.

        Strategy:
        1. Always include the LAST message (current user message).
        2. Always include the FIRST user message (establishes topic).
        3. Fill remaining budget from most recent messages backward.
        4. If truncated, prepend a note so the LLM knows prior context exists.

        Replaces the old conversation_history[-20:] hard slice.
        """
        history = self.conversation_history
        if not history:
            return []

        budget = MAX_CONTEXT_TOKENS - SYSTEM_PROMPT_BUDGET - TOOL_DEFS_BUDGET

        # Short history fits entirely
        total_tokens = sum(self._message_tokens(m) for m in history)
        if total_tokens <= budget:
            return list(history)

        # Find the first user message
        first_user_idx = None
        for i, msg in enumerate(history):
            if msg.get("role") == "user":
                first_user_idx = i
                break

        # Greedily include messages from the end
        selected_tail: List[Dict[str, Any]] = []
        tail_tokens = 0

        for msg in reversed(history):
            msg_tok = self._message_tokens(msg)
            if tail_tokens + msg_tok > budget:
                break
            selected_tail.insert(0, msg)
            tail_tokens += msg_tok

        # Prepend first user message if it wasn't included and fits
        if first_user_idx is not None:
            first_msg = history[first_user_idx]
            if first_msg not in selected_tail:
                first_msg_tok = self._message_tokens(first_msg)
                if tail_tokens + first_msg_tok + 30 <= budget:
                    selected_tail.insert(0, first_msg)
                    tail_tokens += first_msg_tok

        # Prepend truncation note if we dropped messages
        n_total = len(history)
        n_kept = len(selected_tail)
        n_dropped = n_total - n_kept

        if n_dropped > 0:
            truncation_note = {
                "role": "system",
                "content": (
                    f"[Context note: This conversation has {n_total} messages. "
                    f"The {n_dropped} oldest messages were omitted to fit the context window. "
                    f"The messages shown below are the most recent.]"
                ),
            }
            selected_tail.insert(0, truncation_note)
            logger.info(
                f"Context window: kept {n_kept}/{n_total} messages "
                f"(~{tail_tokens} tokens), dropped {n_dropped}"
            )

        return selected_tail

    # ══════════════════════════════════════════════════════════════
    #  SUGGESTED FOLLOW-UPS
    # ══════════════════════════════════════════════════════════════

    def generate_follow_ups(self, assistant_response: str) -> List[str]:
        """Generate 2-3 contextual follow-up questions based on the conversation.

        Makes a lightweight, separate Groq call with a focused prompt.
        Returns a list of short question strings, or empty list on failure.
        """
        last_user_msg = ""
        for msg in reversed(self.conversation_history):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        if not last_user_msg or not assistant_response:
            return []

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate follow-up questions for a brain tumor classification app's AI assistant. "
                            "Given the user's last question and the assistant's response, generate exactly 3 short, "
                            "natural follow-up questions the user might want to ask next. "
                            "Rules:\n"
                            "- Each question must be under 50 characters\n"
                            "- Questions should be diverse (don't repeat the same angle)\n"
                            "- At least one should reference the user's data (scans, history, stats)\n"
                            "- Keep a warm, clinical tone\n"
                            "- Return ONLY a JSON array of 3 strings, nothing else\n"
                            'Example: ["What does this confidence score mean?","Show my scan history","How is glioma treated?"]'
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"User asked: {last_user_msg[:200]}\n\nAssistant replied: {assistant_response[:500]}",
                    },
                ],
                max_tokens=200,
                temperature=0.8,
            )

            raw = response.choices[0].message.content or ""
            raw = raw.strip().strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()

            suggestions = json.loads(raw)

            if isinstance(suggestions, list):
                suggestions = [
                    s.strip() for s in suggestions if isinstance(s, str) and s.strip()
                ][:3]
                logger.info(f"Generated {len(suggestions)} follow-up suggestions")
                return suggestions

            return []

        except Exception as e:
            logger.warning(f"Failed to generate follow-ups: {e}")
            return []

    # ══════════════════════════════════════════════════════════════
    #  GROQ API CALL WITH RETRY
    # ══════════════════════════════════════════════════════════════

    def _call_groq_with_retry(self, use_tools: bool = True):
        """Make a Groq API call with exponential backoff retry.

        Uses token-aware context window management instead of a hard slice.
        """
        context_messages = self._build_context_messages()

        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.get_system_prompt()},
                *context_messages,
            ],
            "max_tokens": self.max_tokens,
            "temperature": 0.7,
        }
        if use_tools:
            kwargs["tools"] = self.get_tools()

        last_exception = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.client.chat.completions.create(**kwargs)
                return response.choices[0].message

            except Exception as e:
                last_exception = e
                error_str = str(e).lower()

                is_rate_limit = "rate_limit" in error_str or "429" in error_str
                is_server_error = any(
                    code in error_str for code in ("500", "502", "503", "504")
                )
                is_timeout = "timeout" in error_str or "connect" in error_str

                if is_rate_limit or is_server_error or is_timeout:
                    if attempt < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                        logger.warning(
                            f"Groq API error (attempt {attempt}/{MAX_RETRIES}): {e}. "
                            f"Retrying in {delay}s..."
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(
                            f"Groq API error after {MAX_RETRIES} attempts: {e}"
                        )
                        raise
                else:
                    logger.error(f"Non-retryable Groq API error: {e}")
                    raise

        raise last_exception

    def _call_groq(self, use_tools: bool = True):
        return self._call_groq_with_retry(use_tools=use_tools)

    async def send_message(self, user_message: str) -> AsyncIterator[str]:
        """Send message and get response.

        Handles the full agentic loop: LLM call → tool execution → LLM call with results.
        Only yields the FINAL text response — never intermediate preambles.
        Tool-call messages are persisted to DB inside the loop.

        IMPORTANT: The user message is already saved to DB and loaded into
        conversation_history by _load_history_from_db() before this method
        is called. Do NOT append it again here — that caused a duplicate
        message bug where the LLM saw the same user message twice.
        """
        if (
            not self.conversation_history
            or self.conversation_history[-1].get("content") != user_message
            or self.conversation_history[-1].get("role") != "user"
        ):
            self.conversation_history.append({"role": "user", "content": user_message})
            logger.warning(
                "User message not found at end of loaded history — appended manually"
            )

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Agent iteration {iteration}")

            try:
                message = self._call_groq_with_retry(use_tools=True)

                # ── Path A: Structured tool calls ────────────────────
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

                    self.conversation_history.append(
                        {
                            "role": "assistant",
                            "content": message.content or "",
                            "tool_calls": tool_calls_list,
                        }
                    )

                    crud_conversation.save_message(
                        self.db,
                        conversation_id=self.conversation_id,
                        role=MessageRole.assistant,
                        content=message.content or "",
                        tool_name="__tool_request__",
                        tool_input=tool_calls_list,
                    )

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

                    continue

                # ── Path B: Inline tool call ─────────────────────────
                text_response = message.content or ""

                inline_call = self._parse_inline_tool_call(text_response)
                if inline_call:
                    logger.info(f"Detected inline tool call: {inline_call['name']}")

                    tool_result = await self.execute_tool(
                        inline_call["name"], inline_call["arguments"]
                    )

                    synthetic_id = f"inline_{inline_call['name']}_{iteration}"

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

                    continue

                # ── Path C: Final text response ──────────────────────
                logger.info("AI finished - sending final response")

                self.conversation_history.append(
                    {"role": "assistant", "content": text_response}
                )

                yield text_response
                break

            except Exception as e:
                error_str = str(e)
                logger.exception("Error in agent loop")

                if "rate_limit" in error_str.lower() or "429" in error_str:
                    wait_match = re.search(
                        r"try again in (\d+m[\d.]+s|\d+s)", error_str, re.IGNORECASE
                    )
                    wait_time = wait_match.group(1) if wait_match else "a few minutes"
                    yield f"__ERROR_RATE_LIMIT__{wait_time}"
                    break

                if "tool_use_failed" in error_str or "400" in error_str:
                    logger.warning("Tool call failed, retrying without tools")
                    try:
                        message = self._call_groq_with_retry(use_tools=False)
                        text_response = message.content or ""
                        self.conversation_history.append(
                            {"role": "assistant", "content": text_response}
                        )
                        yield text_response
                    except Exception as retry_err:
                        retry_str = str(retry_err)
                        if "rate_limit" in retry_str.lower() or "429" in retry_str:
                            wait_match = re.search(
                                r"try again in (\d+m[\d.]+s|\d+s)",
                                retry_str,
                                re.IGNORECASE,
                            )
                            wait_time = (
                                wait_match.group(1) if wait_match else "a few minutes"
                            )
                            yield f"__ERROR_RATE_LIMIT__{wait_time}"
                        else:
                            logger.exception("Retry without tools also failed")
                            yield "__ERROR_SERVER__"
                    break

                if "timeout" in error_str.lower() or "connect" in error_str.lower():
                    yield "__ERROR_TIMEOUT__"
                    break

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
