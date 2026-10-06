"""Twilio webhook signature validation dependency.

Verifies the X-Twilio-Signature header on inbound TwiML webhook requests so
only genuine Twilio callbacks can drive call behavior. Applied as a
router-level dependency on the TwiML router, mirroring verify_api_key.
"""

import logging

from fastapi import HTTPException, Request, status
from twilio.request_validator import RequestValidator

from ..config import settings

logger = logging.getLogger(__name__)


async def verify_twilio_signature(request: Request) -> None:
    """Reject requests lacking a valid X-Twilio-Signature.

    Raises:
        HTTPException 403: signature missing or invalid.
        HTTPException 500: validation required but TWILIO_AUTH_TOKEN unset.
    """
    # Explicit, development-only bypass: requires BOTH the flag AND dev env.
    if not settings.twilio_validate_signature and settings.environment == "development":
        logger.warning("Twilio signature validation BYPASSED (development only)")
        return

    if not settings.twilio_auth_token:
        logger.error(
            "TWILIO_AUTH_TOKEN not configured — cannot validate Twilio request"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Twilio auth token not configured on server",
        )

    # Twilio signs the exact public URL it called (scheme + host + path),
    # reconstructed from configured public host (not the internal ingress host).
    url = f"{settings.twilio_public_base_url}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    form = await request.form()
    params = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")

    validator = RequestValidator(settings.twilio_auth_token)
    if not validator.validate(url, params, signature):
        logger.warning(
            "Invalid Twilio signature — rejecting request",
            extra={"path": request.url.path},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )
