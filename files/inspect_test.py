#!/usr/bin/env python3
"""
Read the zenlabs SDK's session models + enums straight from the installed
package — no client, no token, no network. Run with the venv active:

    python inspect_models.py

Paste the entire output back.
"""

import zenlabs_sdk as z


def dump_model(name: str) -> None:
    print(f"\n{'=' * 72}\n{name}\n{'=' * 72}")
    cls = getattr(z, name, None)
    if cls is None:
        print("  <not exported>")
        return
    fields = getattr(cls, "model_fields", None)
    if fields:
        for fname, f in fields.items():
            print(f"  {fname}: {getattr(f, 'annotation', '?')}")
    else:
        attrs = [a for a in dir(cls) if not a.startswith("_")]
        print("  (not a pydantic model) public attrs:", attrs)


def dump_enum(name: str) -> None:
    print(f"\n{'=' * 72}\n{name}\n{'=' * 72}")
    cls = getattr(z, name, None)
    if cls is None:
        print("  <not exported>")
        return
    try:
        for member in cls:
            print(f"  {member.name} = {member.value!r}")
    except TypeError:
        print("  (not an iterable enum):", repr(cls))


print("MODELS")
for m in [
    "DashboardVoiceSession",
    "InteractionSession",
    "VoiceSession",
    "DashboardSessionAgent",
    "TurnMetrics",
    "SpanMetrics",
]:
    dump_model(m)

print("\n\nENUMS")
for e in [
    "DispositionEnum",
    "CallOutcomeEnum",
    "OutcomeTypeEnum",
    "DispositionSentimentEnum",
    "LanguageEnum",
    "DirectionEnum",
    "ChannelEnum",
    "VoicemailActionEnum",
]:
    dump_enum(e)