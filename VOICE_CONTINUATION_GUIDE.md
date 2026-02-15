# Voice Conversation Continuation Feature

## Overview

This feature enables natural conversation flow when using Skippy with Home Assistant's Wyoming voice satellites. When Skippy asks a follow-up question, the microphone stays active without requiring the wake word to be repeated.

**Example:**
```
User:    "Hey Skippy, turn on the lights"
Skippy:  "Which room's lights?" ← Mic stays open
User:    "The office" ← No wake word needed
Skippy:  "Office lights are now on"
```

## What Was Implemented

### 1. Skippy V2 Backend (`src/skippy/main.py`)

- Added `continue_conversation: bool = False` field to `VoiceResponse` model
- Implemented automatic question detection: responses ending with `?`, `;`, or `？` trigger `continue_conversation=true`
- Enhanced system prompt to guide Skippy to end follow-up questions with question marks

### 2. Home Assistant Custom Component (`custom_components/skippy_v2/`)

Created a brand-new Skippy V2-specific integration with 6 files:

- **manifest.json** - Integration metadata
- **__init__.py** - Setup and lifecycle management
- **const.py** - Configuration constants
- **conversation.py** - Conversation agent implementation (handles webhook requests)
- **config_flow.py** - UI configuration flow for easy setup
- **strings.json** - UI strings and error messages

The custom component:
- POSTs to `/webhook/skippy` endpoint
- Extracts `continue_conversation` flag from response
- Sets it on `ConversationResult` before returning to HA

## How It Works

1. **User speaks** into Wyoming satellite with wake word
2. **HA Assist** captures speech → converts to text
3. **Custom component** POSTs to Skippy V2 at `/webhook/skippy`
4. **Skippy LLM** processes request and generates response
5. **Backend detects** if response ends with question mark (`?`)
6. **Response returned** with `continue_conversation: true/false` flag
7. **HA Assist** receives flag:
   - If `true` → keeps microphone active (no wake word needed for follow-up)
   - If `false` → closes microphone (wake word needed to start new conversation)
8. **Wyoming satellite** respects the flag via TTS/pipeline

## Testing

The feature has been tested and works correctly:

```bash
# Test with follow-up question (returns continue_conversation: true)
curl -X POST http://localhost:8000/webhook/skippy \
  -H "Content-Type: application/json" \
  -d '{"text": "which light?", "conversation_id": "test-1"}'

# Response:
# {
#   "response": "You gotta be a bit more specific, monkey...",
#   "response_text": "...",
#   "continue_conversation": true
# }
```

## Deployment to Home Assistant

### Option A: Development (Symlink - Recommended)

If your Home Assistant runs on the same machine or network:

```bash
# SSH into Home Assistant OS (or use Terminal add-on)
ln -s /path/to/Skippy_V2/custom_components/skippy_v2 /config/custom_components/skippy_v2

# Restart Home Assistant
# Settings > System > Restart Home Assistant
```

### Option B: Production (Copy)

Copy the entire directory:

```bash
# From your development machine
scp -r /home/nolan/Skippy_V2/custom_components/skippy_v2 \
  user@homeassistant:/config/custom_components/

# Or use HA's File Editor / Studio Code Server add-on to upload manually
```

## Configuration in Home Assistant

1. **Restart Home Assistant** to load the new integration
   - Settings > System > Restart Home Assistant

2. **Add the Integration:**
   - Settings > Devices & Services > Add Integration
   - Search for "Skippy V2"
   - Enter webhook URL: `http://<skippy-lxc-ip>:8000/webhook/skippy`
   - Set timeout: `30` seconds
   - Click "Submit"

3. **Set as Default Conversation Agent:**
   - Settings > Voice Assistants > Assist
   - Select "Skippy V2" from the conversation agent dropdown

4. **Verify in HA Logs:**
   - Settings > System > Logs
   - Filter: `skippy_v2`
   - Expected: `Response: ... | Continue: True` messages

## Live Testing with Wyoming Satellite

1. **Basic Test (Statement - Mic Closes):**
   ```
   User: "Hey Skippy, what's the weather?"
   Skippy: "It's sunny and 72 degrees." ← Ends with period, mic closes
   (Wake word required for next request)
   ```

2. **Follow-Up Test (Question - Mic Stays Open):**
   ```
   User: "Hey Skippy, turn on the lights"
   Skippy: "Which room's lights?" ← Ends with question mark, mic stays open
   User: "The office" ← No wake word needed!
   Skippy: "Office lights are now on." ← Mic closes
   (Wake word required for next request)
   ```

3. **Multi-Turn Test:**
   ```
   User: "Hey Skippy, set a reminder"
   Skippy: "What should I remind you about?" ← Mic stays open
   User: "Take out the trash"
   Skippy: "When should I remind you?" ← Mic stays open
   User: "Tomorrow at 7 PM"
   Skippy: "Reminder set." ← Mic closes
   ```

## System Prompt Guidance

The VOICE_SYSTEM_PROMPT in `src/skippy/agent/prompts.py` has been enhanced to instruct Skippy:

> "When you need clarification or more information from the user, ALWAYS end your response with a question mark ("?"). This keeps the microphone active in Home Assistant so the user doesn't need to say the wake word again."

Examples:
- ✅ "Which room's lights?" (ends with ?)
- ✅ "What time?" (ends with ?)
- ✅ "Do you want office lights or bedroom lights?" (ends with ?)
- ❌ "I need more info" (no question mark - mic closes)

## Troubleshooting

### Microphone closes even after a question
- Check HA logs for: `DEBUG ... Continue: True`
- Verify response actually ends with `?`, `;`, or `？`
- Non-English question marks might not be detected (add to const if needed)

### Integration not showing up in HA
- Ensure custom component is in `/config/custom_components/skippy_v2/`
- All 6 files must be present
- Restart Home Assistant (not reload)
- Check HA logs for integration errors

### Webhook connection fails
- Verify Skippy V2 is running: `curl http://localhost:8000/health`
- Check firewall: port 8000 must be accessible from HA machine
- Verify webhook URL is correct in HA config

### Timeout errors
- Increase timeout value in HA integration settings (max 120 seconds)
- Check Skippy logs for slow response times
- Verify OpenAI API key and rate limits

## Files Modified/Created

```
✅ CREATED:
  custom_components/skippy_v2/
    ├── manifest.json
    ├── __init__.py
    ├── const.py
    ├── conversation.py
    ├── config_flow.py
    └── strings.json

✅ MODIFIED:
  src/skippy/main.py
    - Added continue_conversation field to VoiceResponse
    - Added question detection logic

  src/skippy/agent/prompts.py
    - Enhanced VOICE_SYSTEM_PROMPT with question mark guidance

✅ TESTED:
  - Voice endpoint returns correct continue_conversation flag
  - Question detection works for ?, ;, and ？
  - Custom component config flow validates webhook URL
```

## Next Steps

1. Deploy custom component to Home Assistant
2. Add Skippy V2 integration via HA UI
3. Set as default conversation agent
4. Test with Wyoming satellite
5. Enjoy natural conversations without wake word repetition!

## Questions or Issues?

Refer back to the implementation plan at `/home/nolan/.claude/plans/purring-hatching-gizmo.md` for detailed technical information.
