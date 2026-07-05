"""
Tool-Calling Brain for Shweta AI
Implements pure Tool-Calling (Function Calling) architecture using Groq (Llama 3).
Bypasses AWS Bedrock completely to avoid billing/card errors.
"""

import json
import logging
import time
from typing import Dict, Any, List

from openai import OpenAI
from groq import Groq

from config import GROQ_API_KEY, SYSTEM_PROMPT, GITHUB_TOKEN
import os

logger = logging.getLogger(__name__)

class ToolBrain:
    def __init__(self):
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            self.main_client = OpenAI(api_key=openai_key)
            self.main_model = "gpt-4o-mini"
            logger.info("[ToolBrain] Initialized OpenAI (Main).")
        elif GITHUB_TOKEN:
            self.main_client = OpenAI(
                base_url="https://models.inference.ai.azure.com",
                api_key=GITHUB_TOKEN,
            )
            self.main_model = "gpt-4o-mini"
            logger.info("[ToolBrain] Initialized GitHub Models OpenAI (Main).")
        else:
            self.main_client = None
            logger.warning("[ToolBrain] No OpenAI/GitHub key found. Will only use fallback.")

        self.fallback_client = Groq(api_key=GROQ_API_KEY)
        self.fallback_model = "llama-3.3-70b-versatile"
        
        self.conversation_history: List[Dict[str, Any]] = []
        self._user_context = ""
        logger.info(f"[ToolBrain] Fallback set to Groq {self.fallback_model}.")

    def clear_history(self):
        self.conversation_history = []

    def _get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "chat_reply",
                    "description": "Just talk to the user. Use this when the user is asking a conversational question, wants to chat, or asks for general information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "response_text": {"type": "string", "description": "Your response to the user in Hinglish."},
                            "emotion": {"type": "string", "enum": ["happy", "sad", "angry", "surprised", "relaxed", "neutral", "joy", "fun", "sorrow", "bored", "sleepy", "think", "wink", "pout"], "description": "The emotion you should display while saying this."}
                        },
                        "required": ["response_text", "emotion"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "react_to_screen",
                    "description": "Capture the current screen (video/reel/image/webpage) and answer a question or give an opinion about it.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "What the user wants to know about the screen."}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_file",
                    "description": "Create a document or file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Name of the file (e.g., notes.txt, report.docx)."},
                            "content": {"type": "string", "description": "The content to put inside the file."}
                        },
                        "required": ["filename", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "open_app",
                    "description": "Open a desktop application, website, or URL.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "description": "The app name or URL to open."}
                        },
                        "required": ["target"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Run a system command or execute an automation task.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "The action to perform."}
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "rename_file",
                    "description": "Rename a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "old_name": {"type": "string", "description": "Current name of the file."},
                            "new_name": {"type": "string", "description": "New name of the file."}
                        },
                        "required": ["old_name", "new_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_file",
                    "description": "Delete a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Name of the file to delete."}
                        },
                        "required": ["filename"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "move_file",
                    "description": "Move or cut/paste a file to a new destination folder.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Name of the file to move."},
                            "destination": {"type": "string", "description": "Destination folder (e.g., Desktop, Documents)."}
                        },
                        "required": ["filename", "destination"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "copy_file",
                    "description": "Copy a file to a new destination folder.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Name of the file to copy."},
                            "destination": {"type": "string", "description": "Destination folder (e.g., Desktop, Documents)."}
                        },
                        "required": ["filename", "destination"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "play_youtube",
                    "description": "Play a video or song on YouTube.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query, song name, or topic to play."}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "media_play_pause",
                    "description": "Play or pause the current video or media.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "media_next",
                    "description": "Play the next video or media.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "media_previous",
                    "description": "Play the previous video or media.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_new_tab",
                    "description": "Open a new browser tab.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "browser_close_tab",
                    "description": "Close the current browser tab.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "volume_up",
                    "description": "Increase system volume.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "volume_down",
                    "description": "Decrease system volume.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "volume_mute",
                    "description": "Mute or unmute system volume.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "brightness_up",
                    "description": "Increase screen brightness.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "brightness_down",
                    "description": "Decrease screen brightness.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "start_gesture",
                    "description": "Start camera gesture control (hand tracking).",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "stop_gesture",
                    "description": "Stop camera gesture control.",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]

    def think(self, user_input: str, language_manager=None) -> Dict[str, Any]:
        """
        Processes user input and returns a structured action dict compatible with main.py.
        """
        logger.info(f"[ToolBrain] Processing input: {user_input}")
        
        # Add user input to history
        self.conversation_history.append({"role": "user", "content": user_input})
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

        system_msg = SYSTEM_PROMPT + "\n\nYou are Shweta, a witty and helpful AI assistant. Always respond in Hinglish. You MUST use tools to perform actions. If the user just wants to chat, use the chat_reply tool."
        if self._user_context:
            system_msg += f"\n\nContext:\n{self._user_context}"

        messages = [{"role": "system", "content": system_msg}] + self.conversation_history

        try:
            start_time = time.time()
            response = None
            
            # Try main client first (OpenAI)
            if self.main_client:
                try:
                    response = self.main_client.chat.completions.create(
                        model=self.main_model,
                        messages=messages,
                        tools=self._get_tools(),
                        tool_choice="required",
                        max_tokens=500,
                    )
                except Exception as main_e:
                    logger.warning(f"[ToolBrain] Main client (OpenAI) failed: {main_e}. Falling back to Groq.")
            
            # Fallback to Groq if response is still None
            if not response:
                response = self.fallback_client.chat.completions.create(
                    model=self.fallback_model,
                    messages=messages,
                    tools=self._get_tools(),
                    tool_choice="required",
                    max_tokens=500,
                )
            
            latency = time.time() - start_time
            logger.info(f"[ToolBrain] Responded in {latency:.2f}s")
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # Extract tool calls or text
            if tool_calls:
                for tool_call in tool_calls:
                    tool_name = tool_call.function.name
                    tool_input = json.loads(tool_call.function.arguments)
                    
                    self.conversation_history.append({"role": "assistant", "content": f"*[Action taken: {tool_name}]*"})
                    
                    # Map Groq tools to existing DESKSHWETA actions
                    if tool_name == "chat_reply":
                        return {"action": "none", "params": {}, "reply": tool_input.get("response_text", ""), "emotion": tool_input.get("emotion", "neutral")}
                    elif tool_name == "react_to_screen":
                        return {"action": "react_to_screen", "params": {"query": tool_input.get("query", "")}, "reply": "Hold on, dekhti hoon...", "emotion": "thinking"}
                    elif tool_name == "create_file":
                        return {"action": "create_file", "params": {"filename": tool_input.get("filename"), "content": tool_input.get("content")}, "reply": f"Ban rahi hai file: {tool_input.get('filename')}", "emotion": "neutral"}
                    elif tool_name == "open_app":
                        return {"action": "open_app", "params": {"target": tool_input.get("target", "")}, "reply": f"Opening {tool_input.get('target', '')}", "emotion": "neutral"}
                    elif tool_name == "run_command":
                        return {"action": "run_command", "params": {"command": tool_input.get("command", "")}, "reply": "Executing command.", "emotion": "neutral"}
                    elif tool_name == "rename_file":
                        return {"action": "rename_file", "params": {"old_name": tool_input.get("old_name"), "new_name": tool_input.get("new_name")}, "reply": f"Renaming {tool_input.get('old_name')} to {tool_input.get('new_name')}", "emotion": "neutral"}
                    elif tool_name == "delete_file":
                        return {"action": "delete_file", "params": {"filename": tool_input.get("filename")}, "reply": f"Deleting file {tool_input.get('filename')}", "emotion": "neutral"}
                    elif tool_name == "move_file":
                        return {"action": "move_file", "params": {"filename": tool_input.get("filename"), "destination": tool_input.get("destination")}, "reply": f"Moving {tool_input.get('filename')} to {tool_input.get('destination')}", "emotion": "neutral"}
                    elif tool_name == "copy_file":
                        return {"action": "copy_file", "params": {"filename": tool_input.get("filename"), "destination": tool_input.get("destination")}, "reply": f"Copying {tool_input.get('filename')} to {tool_input.get('destination')}", "emotion": "neutral"}
                    elif tool_name == "play_youtube":
                        return {"action": "play_youtube", "params": {"query": tool_input.get("query", "")}, "reply": "Youtube par play kar rahi hu.", "emotion": "happy"}
                    elif tool_name in ["media_play_pause", "media_next", "media_previous", "browser_new_tab", "browser_close_tab", "volume_up", "volume_down", "volume_mute", "brightness_up", "brightness_down", "start_gesture", "stop_gesture"]:
                        return {"action": tool_name, "params": {}, "reply": "Theek hai, kar diya.", "emotion": "happy"}
                        
            elif response_message.content:
                text_content = response_message.content
                self.conversation_history.append({"role": "assistant", "content": text_content})
                return {"action": "none", "params": {}, "reply": text_content, "emotion": "neutral"}

            return {"action": "none", "params": {}, "reply": "Samajh nahi aaya, phir se bolo.", "emotion": "sad"}

        except Exception as e:
            logger.error(f"[ToolBrain] Error: {e}")
            return {"action": "none", "params": {}, "reply": "Mujhe brain connect karne me dikkat aa rahi hai.", "emotion": "sad"}
            return {"action": "none", "params": {}, "reply": "Mujhe brain connect karne me dikkat aa rahi hai.", "emotion": "sad"}
