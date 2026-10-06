# 1. Telephony behind a port, with two implementations

Status: accepted

## Context

The agent never sees raw audio. Voice activity detection, chunking, speech-to-text and
text-to-speech all belong to the telephony layer, which means turn boundaries are decided outside
this system. What crosses the boundary is a turn: text in, a reply out.

That makes telephony the most obvious candidate for a port. It also makes it the easiest one to get
wrong, because a seam with a single implementation behind it is a guess about what varies. Plenty
of codebases have an `interface` that has only ever been satisfied by one class and leaks its
assumptions everywhere.

There was a second pressure. A POC that only runs if the reader owns a Twilio account and a phone
number is a POC almost nobody runs.

## Options considered

1. **Couple directly to ConversationRelay.** Shortest path. The message shapes are pleasant and the
   protocol is small. Every handler ends up knowing about `voicePrompt` and `last`.
2. **Abstract, but ship one implementation.** The usual compromise. Costs the indirection without
   ever testing whether the abstraction holds.
3. **Two live implementations behind one interface.** More work, and the only version that proves
   anything.

## Decision

Option 3. One turn-shaped interface with two implementations that both have to keep working:
Twilio ConversationRelay over the PSTN, and the browser Web Speech API.

The browser path is the default quick start precisely because it needs no account. The phone path
is the one that has to survive contact with a real network.

## Consequences

The seam is real rather than aspirational, and the repo can say so honestly: above the port,
nothing knows which implementation is underneath.

Keeping two paths working costs something on every change to the session handler, and the two
disagree in ways worth knowing about. Twilio decides end-of-speech for you and the browser does
not, so barge-in and turn segmentation are not symmetric. That asymmetry is a property of the
domain, not of the abstraction, and surfacing it is part of what the second implementation bought.

The browser path also changes the privacy story: Chrome's recogniser is Google's cloud one, so
audio leaves the machine on a path that otherwise runs entirely locally. That is documented rather
than hidden.
