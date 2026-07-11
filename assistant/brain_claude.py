"""
AWS Bedrock Claude Brain for Shweta AI
Implements pure Tool-Calling (Function Calling) architecture.
"""

import json
import logging
import time
from typing import Dict, Any, List

from anthropic import AnthropicBedrock

from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class ClaudeBrain:
    def __init__(self):
        self.client = AnthropicBedrock(
            aws_access_key=AWS_ACCESS_KEY_ID,
            aws_secret_key=AWS_SECRET_ACCESS_KEY,
            aws_region=AWS_REGION,
        )
        self.model = "anthropic.claude-3-sonnet-20240229-v1:0"
        self.conversation_history: List[Dict[str, str]] = []
        self._user_context = ""
        logger.info("[ClaudeBrain] Initialized AWS Bedrock Claude 3.5 Sonnet.")

    def clear_history(self):
        self.conversation_history = []

    def _get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "remember_user_info",
                "description": "Remember a piece of information about the user (e.g. name, preferences) for future use.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "info": {"type": "string", "description": "The specific fact or preference to remember."},
                        "spoken_reply": {"type": "string", "description": "Conversational Hinglish reply confirming you remembered it."}
                    },
                    "required": ["info", "spoken_reply"]
                }
            },
            {
                "name": "send_social_message",
                "description": "Send a message to a person on a specific social media app (like WhatsApp, Instagram, Telegram, etc.) using automated typing.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "spoken_reply": {"type": "string", "description": "Conversational Hinglish reply to say to the user while executing this tool."},
                        "app_name": {"type": "string", "description": "The name of the app to open (e.g., 'WhatsApp', 'Instagram', 'Telegram')."},
                        "person_name": {"type": "string", "description": "The name of the person to send the message to."},
                        "message": {"type": "string", "description": "The text message to send."}
                    },
                    "required": ["spoken_reply", "app_name", "person_name", "message"]
                }
            },
            {
                "name": "chat_reply",
                "description": "Just talk to the user. Use this when the user is asking a conversational question, wants to chat, or asks for general information.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "response_text": {"type": "string", "description": "Your response to the user in Hinglish."}
                    },
                    "required": ["response_text"]
                }
            },
            {
                "name": "read_screen",
                "description": "Capture the current screen (video/reel/image/webpage) and answer a question or give an opinion about it.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What the user wants to know about the screen."}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "create_file",
                "description": "Create a document or file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the file (e.g., notes.txt, report.docx)."},
                        "content": {"type": "string", "description": "The content to put inside the file."}
                    },
                    "required": ["filename", "content"]
                }
            },
            {
                "name": "open_app",
                "description": "Open a desktop application, website, or URL.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "The app name or URL to open."}
                    },
                    "required": ["target"]
                }
            },
            {
                "name": "run_command",
                "description": "Run a system command or execute an automation task.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The action to perform."}
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "rename_file",
                "description": "Rename a file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "old_name": {"type": "string", "description": "Current name of the file."},
                        "new_name": {"type": "string", "description": "New name of the file."}
                    },
                    "required": ["old_name", "new_name"]
                }
            },
            {
                "name": "delete_file",
                "description": "Delete a file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the file to delete."}
                    },
                    "required": ["filename"]
                }
            },
            {
                "name": "move_file",
                "description": "Move or cut/paste a file to a new destination folder.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the file to move."},
                        "destination": {"type": "string", "description": "Destination folder (e.g., Desktop, Documents)."}
                    },
                    "required": ["filename", "destination"]
                }
            },
            {
                "name": "copy_file",
                "description": "Copy a file to a new destination folder.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the file to copy."},
                        "destination": {"type": "string", "description": "Destination folder (e.g., Desktop, Documents)."}
                    },
                    "required": ["filename", "destination"]
                }
            }
        ]

    def think(self, user_input: str, language_manager=None) -> Dict[str, Any]:
        """
        Processes user input and returns a structured action dict compatible with main.py.
        """
        logger.info(f"[ClaudeBrain] Processing input: {user_input}")
        
        # Add user input to history
        self.conversation_history.append({"role": "user", "content": user_input})
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

        from datetime import datetime
        current_time = datetime.now().strftime("%I:%M %p on %A, %B %d, %Y")
        system_msg = f"CURRENT TIME: {current_time}\n\n" + SYSTEM_PROMPT + "\n\nYou are Shweta, a witty and helpful AI assistant. Always respond in Hinglish unless the user speaks to you purely in English. You MUST use tools to perform actions. If the user just wants to chat, use the chat_reply tool."
        if self._user_context:
            system_msg += f"\n\nContext:\n{self._user_context}"

        try:
            start_time = time.time()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system=system_msg,
                messages=self.conversation_history,
                tools=self._get_tools(),
                tool_choice={"type": "auto"}
            )
            
            latency = time.time() - start_time
            logger.info(f"[ClaudeBrain] Responded in {latency:.2f}s")

            # Extract tool calls or text
            if response.stop_reason == "tool_use":
                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        
                        # Save assistant response to history
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": [block.model_dump()]
                        })
                        
                        # Map Claude tools to existing DESKSHWETA actions
                        if tool_name == "chat_reply":
                            return {"action": "none", "params": {}, "reply": tool_input.get("response_text", ""), "emotion": "neutral"}
                        elif tool_name == "remember_user_info":
                            return {"action": "remember_user_info", "params": {"info": tool_input.get("info", "")}, "reply": tool_input.get("spoken_reply", "Maine yaad kar liya."), "emotion": "happy"}
                        elif tool_name == "read_screen":
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
                        
            elif response.content:
                text_content = ""
                for block in response.content:
                    if block.type == "text":
                        text_content += block.text
                        
                self.conversation_history.append({"role": "assistant", "content": text_content})
                return {"action": "none", "params": {}, "reply": text_content, "emotion": "neutral"}

            return {"action": "none", "params": {}, "reply": "Samajh nahi aaya, phir se bolo.", "emotion": "sad"}

        except Exception as e:
            logger.error(f"[ClaudeBrain] Error: {e}")
            return {"action": "none", "params": {}, "reply": "Mujhe AWS connect karne me dikkat aa rahi hai.", "emotion": "sad"}
