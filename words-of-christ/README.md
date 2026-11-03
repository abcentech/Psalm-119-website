# The Red Letters — four Gospel read-aloud reader

**Live website:** https://abcentech.github.io/Psalm-119-website/words-of-christ/

This is a separate GitHub Pages-hosted Scripture reader, not the KidsInspiring Nation website. The **entire King James Version red-letter corpus is embedded in the HTML file**: 39,350 words, 1,943 speech segments, 85 reading chapters across John, Matthew, Mark and Luke. It does not fetch chapter data from an API. The red-letter boundaries are editorial and may differ by Bible edition.

## Reading

Select a Gospel and chapter; tap a verse number to begin. You can choose:
- **This chapter only** — stops at the chapter boundary.
- **Entire book, continuously** — reads sequentially to the end of the selected Gospel, including moving to the next chapter automatically.
- **All four Gospels, continuously** — advances through each available chapter.
- **Repeat selected verse** — repeats the selected verse (including split speech segments) indefinitely or 3, 5, 10 or 20 times.

Enter a command in the **Tell the reader what to do** field, including:
- `Read John` — starts John at chapter 1 and reads all of John without requiring another click.
- `Read John 3`, `Read John chapter 3`, `Read Luke 5:12`.
- `Loop John 3:16`, `Repeat John 3:16 five times`, `Loop John 3:16-18`, `Loop this verse`.
- `Pause`, `Continue`, and `Stop`.

The microphone command button uses the browser Web Speech Recognition implementation, **only if supported**; typing commands works without it.

## Voices and limitations

The three **accent preferences** are British English (`en-GB`), American English (`en-US`), and Nigerian English (`en-NG`). Only voices **actually installed/exposed by the visitor's browser** are selectable. The reader will never relabel an American or British voice as Nigerian when `en-NG` isn't available. Click Preview to compare available voices. Voices with names indicating Natural, Neural, Premium, or Enhanced are sorted first when the system supplies them.

This static GitHub Pages project does **not** claim to provide professional premium studio/neural narration itself. High-quality consistent UK, US, and Nigerian voice generation requires an authorized cloud speech service or properly licensed prerecorded content. A trial of an unofficial, unauthenticated neural TTS endpoint returned HTTP 403 in CI, so it was not added to the user-facing reader. An official Azure Speech integration with securely provisioned credentials (and an audio generation pipeline) would be the appropriate next step for guaranteed natural voices. Microsoft currently lists `en-GB-SoniaNeural`, `en-US-JennyNeural`, and `en-NG-EzinneNeural` as examples of such voices.

Audio follows browser `speechSynthesis` capabilities; some Android devices pause speech when the screen locks or browser moves to the background. Highlighting is event-based when word boundary events are available, and approximate otherwise. Chapter-to-chapter continuation is designed for the active browser tab.

Reading progress and preferences are stored in localStorage on this device only.

## Hosting and deployment

The source is on the `gh-pages` branch at `words-of-christ/index.html`. The standalone site uses only static HTML, CSS and JavaScript, with no external runtime API calls for Scripture. This branch is configured for GitHub Pages and its Pages build workflow should complete after changes.
