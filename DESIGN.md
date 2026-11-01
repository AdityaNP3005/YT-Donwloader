# YouTube Downloader desktop design

The app is a small media utility for saving videos and playlists. The interface
should make adding links, choosing a destination, and following a queue obvious.
Keep the native Tkinter UI and its single-worker download engine.

## Visual direction

- Paper `#f3f7fc`: window background.
- White `#ffffff`: input and queue surfaces.
- Ink `#1c304a`: main text.
- Slate `#64788f`: supporting text.
- Blue `#1672df`: primary actions and the app's play/download mark.
- Rule `#dce6f1`: boundaries between controls and content.

Use Ubuntu Sans when available, with Noto Sans / the system font as fallbacks.
Use one family with a clear hierarchy: 22pt title, 14pt section headings,
12pt body and controls, and 11pt secondary information. Positive Tk font sizes
follow the display DPI. Size padding, row heights, and icons from the rendered
body font metrics.

The composer switches from two columns to stacked sections when the controls
no longer fit side by side. Compact settings put quality and destination on the
same row. Short windows reduce spacing and input height, omit supporting hints,
and move secondary queue actions into menus. Keep control text readable.
The queue takes the remaining height. On narrow windows, show selection, title,
progress and status; quality and format remain in the job detail. The page never
scrolls; only the list of queued videos and log text scroll within their areas.

Left-align content. Give the queue most of the available height. Group the link
composer and destination settings into one working surface rather than a grid of
decorative cards. Keep secondary queue actions separate from the primary start
button. Always pair action icons with text. No background animation.

```text
[app mark] YouTube Downloader                     [Open folder]
           Download videos and playlists
-----------------------------------------------------------------
 Add links                          | Download settings
 [multiline URL input      Paste]   | Quality [1080p]
 [Add to queue] [Inspect] [Stop]     | Destination [........] [Browse]
 [Include playlist]                 |
-----------------------------------------------------------------
 Queue + counts                     [Start download] [Pause] [Cancel]
 [Select all] [Clear selection]           [Retry] [Remove]
 [pick | video title | quality | format | progress | status]
 [                 useful empty-state guidance                ]
 [Details and log]                                 [< Page >]
-----------------------------------------------------------------
 [progress bar]
 Current job / ready state                              speed / ETA
```

Review: removed the old all-caps media label and implementation-heavy idle
message. A permanent navigation sidebar would be decorative because this app has
one queue, so it is deliberately absent. The single memorable visual element is
the original play/download mark. Blue distinguishes the app identity without
pretending this is an official YouTube app. Icons describe real actions, with no
unrelated service logos.

## Assets and desktop identity

`assets/youtube-downloader.svg` is the scalable source logo. PNG sizes support
Tk's `iconphoto`, Ubuntu's app launcher, and the running window icon. Generate
them and the small control icons with `python3 scripts/build_icons.py` (Pillow
needed only while rebuilding assets). Runtime uses only Tkinter's PNG loader.

The Linux launcher uses `StartupWMClass=Youtubedownloader`, matching the Tk root
class. `scripts/install-desktop.sh` installs the user launcher and icon sizes.
