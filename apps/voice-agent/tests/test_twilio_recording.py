import asyncio
import logging

from fastapi import BackgroundTasks

from voice_agent.api.twiml import _build_recording_metadata, recording_status
from voice_agent.voice_ai.async_persistence import persist_recording_metadata
from voice_agent.voice_ai.twilio_protocol import build_twiml


def _xml_text(response) -> str:
    return response.body.decode("utf-8")


def test_build_twiml_includes_start_recording_when_enabled():
    xml = _xml_text(
        build_twiml(
            ws_url="wss://example.com/ws",
            welcome="Hi",
            language="en-US",
            voice="test-voice",
            transcription_provider="Deepgram",
            tts_provider="ElevenLabs",
            recording_enabled=True,
            recording_status_callback_url=(
                "https://example.com/twiml/recording_status"
            ),
            recording_status_callback_event="in-progress completed absent",
            recording_name="voice_ai_recording",
            recording_channels="dual",
            recording_track="both",
        )
    )

    assert "<Start>" in xml
    assert "<Recording" in xml
    assert 'name="voice_ai_recording"' in xml
    assert 'channels="dual"' in xml
    assert 'track="both"' in xml
    assert 'recordingStatusCallback="https://example.com/twiml/recording_status"' in xml
    assert 'recordingStatusCallbackMethod="POST"' in xml
    assert 'recordingStatusCallbackEvent="in-progress completed absent"' in xml
    assert xml.index("<Start>") < xml.index("<Connect")


def test_build_twiml_does_not_include_start_recording_when_disabled():
    xml = _xml_text(
        build_twiml(
            ws_url="wss://example.com/ws",
            welcome="Hi",
            language="en-US",
            voice="test-voice",
            transcription_provider="Deepgram",
            tts_provider="ElevenLabs",
            recording_enabled=False,
            recording_status_callback_url=(
                "https://example.com/twiml/recording_status"
            ),
            recording_status_callback_event="in-progress completed absent",
            recording_name="voice_ai_recording",
            recording_channels="dual",
            recording_track="both",
        )
    )

    assert "<Start>" not in xml
    assert "<Recording" not in xml
    assert "<Connect" in xml
    assert "<ConversationRelay" in xml


class _FakeRequest:
    def __init__(self, form_data):
        self._form_data = form_data

    async def form(self):
        return self._form_data


def test_recording_status_callback_returns_ok_and_does_not_log_recording_url(caplog):
    recording_url = (
        "https://api.twilio.com/2010-04-01/Accounts/AC123/" "Recordings/RE123"
    )

    request = _FakeRequest(
        {
            "AccountSid": "AC123",
            "CallSid": "CA123",
            "RecordingSid": "RE123",
            "RecordingStatus": "completed",
            "RecordingDuration": "19",
            "RecordingChannels": "2",
            "RecordingStartTime": "2026-06-11T23:32:31Z",
            "RecordingTrack": "both",
            "RecordingUrl": recording_url,
        }
    )

    caplog.set_level(logging.INFO, logger="voice_agent.api.twiml")

    result = asyncio.run(recording_status(request, BackgroundTasks()))

    assert result == {"ok": True}

    log_messages = "\n".join(record.getMessage() for record in caplog.records)
    assert recording_url not in log_messages

    matching_records = [
        record
        for record in caplog.records
        if record.getMessage() == "Twilio recording completed callback"
    ]

    assert len(matching_records) == 1

    record = matching_records[0]
    assert record.__dict__.get("account_sid") == "AC123"
    assert record.__dict__.get("call_sid") == "CA123"
    assert record.__dict__.get("recording_sid") == "RE123"
    assert record.__dict__.get("recording_event_status") == "completed"
    assert record.__dict__.get("recording_duration") == "19"
    assert "recording_url" not in record.__dict__


def test_recording_status_callback_logs_absent_as_warning(caplog):
    request = _FakeRequest(
        {
            "AccountSid": "AC123",
            "CallSid": "CA123",
            "RecordingSid": "RE123",
            "RecordingStatus": "absent",
        }
    )

    caplog.set_level(logging.DEBUG, logger="voice_agent.api.twiml")

    result = asyncio.run(recording_status(request, BackgroundTasks()))

    assert result == {"ok": True}

    matching_records = [
        record
        for record in caplog.records
        if record.getMessage() == "Twilio recording absent callback"
    ]

    assert len(matching_records) == 1
    assert matching_records[0].levelno == logging.WARNING
    assert matching_records[0].__dict__.get("recording_event_status") == "absent"


def test_recording_status_callback_logs_in_progress_as_debug(caplog):
    request = _FakeRequest(
        {
            "AccountSid": "AC123",
            "CallSid": "CA123",
            "RecordingSid": "RE123",
            "RecordingStatus": "in-progress",
        }
    )

    caplog.set_level(logging.DEBUG, logger="voice_agent.api.twiml")

    result = asyncio.run(recording_status(request, BackgroundTasks()))

    assert result == {"ok": True}

    matching_records = [
        record
        for record in caplog.records
        if record.getMessage() == "Twilio recording status callback"
    ]

    assert len(matching_records) == 1
    assert matching_records[0].levelno == logging.DEBUG
    assert matching_records[0].__dict__.get("recording_event_status") == "in-progress"


def test_recording_status_schedules_persistence_on_completed():
    request = _FakeRequest(
        {
            "AccountSid": "ACacct1",
            "CallSid": "CAcall123",
            "RecordingSid": "RErec789",
            "RecordingStatus": "completed",
            "RecordingDuration": "19",
            "RecordingChannels": "2",
            "RecordingTrack": "both",
        }
    )

    bg = BackgroundTasks()
    result = asyncio.run(recording_status(request, bg))

    assert result == {"ok": True}
    assert len(bg.tasks) == 1

    task = bg.tasks[0]
    assert task.func is persist_recording_metadata
    call_sid, recording = task.args
    assert call_sid == "CAcall123"
    assert recording["recording_sid"] == "RErec789"
    assert recording["s3_key"] == "ACacct1/RErec789"
    assert recording["status"] == "completed"
    assert recording["duration"] == "19"


def test_recording_status_schedules_persistence_on_in_progress():
    request = _FakeRequest(
        {
            "AccountSid": "ACacct1",
            "CallSid": "CAcall123",
            "RecordingSid": "RErec789",
            "RecordingStatus": "in-progress",
        }
    )

    bg = BackgroundTasks()
    asyncio.run(recording_status(request, bg))

    assert len(bg.tasks) == 1
    _, recording = bg.tasks[0].args
    assert recording["status"] == "in-progress"
    assert "duration" not in recording  # Twilio did not send it


def test_recording_status_does_not_schedule_persistence_without_call_sid():
    request = _FakeRequest({"RecordingStatus": "completed", "RecordingSid": "RErec789"})

    bg = BackgroundTasks()
    result = asyncio.run(recording_status(request, bg))

    assert result == {"ok": True}
    assert bg.tasks == []


def test_build_recording_metadata_derives_s3_key():
    metadata = _build_recording_metadata(
        account_sid="ACacct1",
        recording_sid="RErec789",
        status="completed",
        duration="19",
        channels="2",
        track="both",
        start_time="2026-06-13T10:31:02Z",
    )

    assert metadata["s3_key"] == "ACacct1/RErec789"
    assert metadata["account_sid"] == "ACacct1"
    assert metadata["recording_sid"] == "RErec789"


def test_build_recording_metadata_omits_missing_fields():
    metadata = _build_recording_metadata(
        account_sid=None,
        recording_sid=None,
        status="absent",
        duration=None,
        channels=None,
        track=None,
        start_time=None,
    )

    assert metadata == {"status": "absent"}
