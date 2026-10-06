class PredefinedResponses:
    # --- INIT / SETUP ERRORS ---
    INIT_FAIL = "Sorry, something went wrong initializing the survey."
    START_FAIL = "Sorry, I'm having trouble starting the survey."

    # --- GENERIC PROMPTS ---
    GOODBYE = "Thanks for your time!"
    ALREADY_DONE = "We're already done. Thanks for your time!"
    CLARIFY = "Could you clarify?"
    TRY_AGAIN = "Could you please say that again?"
    TRY_AGAIN_AFTER_LLM_EXCEPTION = (
        "Sorry, I didn't catch that. Could you say it again?"
    )

    # --- VALIDATION AND RETRY MESSAGES ---
    INVALID_OPTION = "Sorry, could you pick one of the options or say it again?"
    SAVE_ERROR = "Sorry, there was a problem saving that. Could you try again?"
    RETRY_ON_TOOL_FAIL = "Let's try that once more."

    # --- COACH HANDOVER ---

    COACH_HANDOVER_FALLBACK_MESSAGE = (
        "I'll connect you with a coach so they can help you directly."
    )

    COACH_HANDOVER_FAILURE_MESSAGE = "Sorry, I'm not able to finish this right now. Let me connect you with someone who can help."
