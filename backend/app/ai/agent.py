import os
import json
import logging
from typing import AsyncIterator, Dict, List, Any, Optional
from sqlalchemy.orm import Session

from groq import Groq  # ← Changed from anthropic

from app.crud import prediction as crud_prediction

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
        """Initialize the chat agent with Groq"""
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.db = db

        # ✅ Initialize Groq client (FREE!)
        self.client = Groq(api_key=api_key or os.getenv("GROQ_API_KEY"))

        self.conversation_history: List[Dict[str, str]] = []
        self.max_tokens = 1024
        # ✅ Use Llama 3.1 70B (best free model)
        self.model = "llama-3.3-70b-versatile"

        logger.info(
            f"ChatAgent initialized for user={self.user_id}, conversation={conversation_id}"
        )

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
1. ⚠️ You are NOT a replacement for medical professionals
2. ⚠️ Always recommend consulting a doctor for medical advice
3. ⚠️ Never make definitive diagnoses or treatment recommendations
4. ⚠️ Be empathetic but factual - balance compassion with accuracy
5. ⚠️ If symptoms seem urgent, strongly recommend immediate medical attention

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

    async def send_message(self, user_message: str) -> AsyncIterator[str]:
        """Send message and get streaming response"""
        # Add user message to history
        self.conversation_history.append({"role": "user", "content": user_message})

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Agent iteration {iteration}")

            try:
                # ✅ Groq API call (OpenAI-compatible)
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.get_system_prompt()},
                        *self.conversation_history,
                    ],
                    tools=self.get_tools(),
                    max_tokens=self.max_tokens,
                    temperature=0.7,
                )

                message = response.choices[0].message

                # Check if AI wants to use tools
                if message.tool_calls:
                    logger.info("AI requested tool use")

                    # Add assistant's tool request to history
                    self.conversation_history.append(
                        {
                            "role": "assistant",
                            "content": message.content or "",
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in message.tool_calls
                            ],
                        }
                    )

                    # Execute each tool
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_input = json.loads(tool_call.function.arguments)

                        logger.info(f"Tool call: {tool_name}({tool_input})")

                        # Execute tool
                        tool_result = await self.execute_tool(tool_name, tool_input)

                        # Add tool result to history
                        self.conversation_history.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(tool_result),
                            }
                        )

                    # Continue loop to get AI's response with tool results
                    continue
                # this else block executes when AI has finished processing and is ready to send a final response @@@@ text
                else:
                    # AI has final text response
                    logger.info("AI finished - sending response")

                    text_response = message.content or ""

                    # Add to history
                    self.conversation_history.append(
                        {"role": "assistant", "content": text_response}
                    )

                    # Yield response
                    yield text_response
                    break

            except Exception as e:
                logger.exception("Error in agent loop")
                yield f"I apologize, but I encountered an error: {str(e)}"
                break

        if iteration >= max_iterations:
            logger.error("Agent hit max iterations")
            yield "I apologize, but I'm having trouble processing your request. Please try a simpler question."

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
