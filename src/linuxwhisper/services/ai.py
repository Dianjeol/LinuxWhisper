"""
AI chat and vision completion service.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from linuxwhisper.api import GROQ_CLIENT
from linuxwhisper.config import CFG
from linuxwhisper.decorators import safe_execute
from linuxwhisper.state import STATE


class AIService:
    """AI chat and vision completion service."""

    @staticmethod
    def smart_route(user_input: str) -> Dict[str, str]:
        """
        Use a fast model to classify the user's intent:
        - DICTATION: Pure transcription/writing.
        - AGENT: Chat, questions, help.
        - VISION: Screen analysis.
        """
        try:
            # Construct the prompt for the router
            prompt = CFG.ROUTER_PROMPT.replace("{input}", user_input)
            
            messages = [{"role": "user", "content": prompt}]
            
            response = GROQ_CLIENT.chat.completions.create(
                model=CFG.MODEL_FAST,
                messages=messages,
                max_tokens=200,
                temperature=0.0 # Deterministic
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON from potential markdown blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.strip("`").strip()
                
            import json
            return json.loads(content)
        except Exception as e:
            print(f"⚠️ Router failed: {e}. Defaulting to AGENT.")
            return {"action": "AGENT", "text": user_input}

    @staticmethod
    def build_messages(user_content: str, selected_text: str = "", image_base64: Optional[str] = None) -> List[Dict[str, Any]]:
        """Build API messages with system prompt, context, and history."""
        messages = [{"role": "system", "content": CFG.SYSTEM_PROMPT}]
        
        # Inject Selected Text Context if available
        if selected_text:
            messages.append({
                "role": "system", 
                "content": f"CONTEXT - SELECTED CONTENT:\n{selected_text}\n(User may refer to this as 'this', 'selection', or 'it')."
            })

        # Append History
        messages.extend(STATE.conversation_history)

        # Build User Message (Text + Optional Image)
        if image_base64:
            content = [
                {"type": "text", "text": user_content},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
            ]
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_content})
            
        return messages

    @staticmethod
    @safe_execute("Aria Router")
    def route_and_process(user_text: str, selected_text: str = "") -> Tuple[str, Optional[str]]:
        """
        Main entry point. Routes input -> Action -> Result.
        Returns: (Action_Type, Result_Text)
        """
        # 1. Fast Route
        route = AIService.smart_route(user_text)
        action = route.get("action", "AGENT").upper()
        processed_text = route.get("text", user_text)
        
        print(f"🔀 Router Decision: {action}")
        
        # 2. Execute Action
        if action == "DICTATION":
            # Return the cleaned text directly
            return "DICTATION", processed_text
            
        elif action == "VISION":
            # Vision Flow: Take screenshot -> Llama 4
            from linuxwhisper.services.image import ImageService # Lazy import
            print("📸 Taking screenshot for Vision request...")
            image_b64 = ImageService.take_screenshot()
            
            # Use original text + screenshot
            response = AIService._process_agent(processed_text, selected_text, image_b64)
            return "VISION", response
            
        else: # AGENT
            # Standard Chat Flow: Input + Context -> Moonshot
            response = AIService._process_agent(processed_text, selected_text, None)
            return "AGENT", response

    @staticmethod
    def _process_agent(user_text: str, selected_text: str = "", image_base64: Optional[str] = None) -> Optional[str]:
        """Internal method to call the heavy Agent/Vision models."""
        messages = AIService.build_messages(user_text, selected_text, image_base64)
        model = CFG.MODEL_VISION if image_base64 else CFG.MODEL_CHAT
        
        response = GROQ_CLIENT.chat.completions.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content
