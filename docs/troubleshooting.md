# Troubleshooting

## Permissions

macOS attaches both permissions to the *running executable*, not to your
terminal, and permission changes never apply to an already-running process —
**relaunch vlow after granting anything**.

1. **Microphone** — auto-prompted on the first recording.
2. **Accessibility** — auto-prompted on launch. Required for the modifier-key
   monitor and the synthesized `Cmd+V`.

The ad-hoc signed build makes macOS treat the app as new whenever its
executable changes — a fresh install, an update, or a rebuilt
`dist/vlow.app`. When that happens:

1. Open **System Settings → Privacy & Security → Accessibility**.
2. Find **vlow** and toggle it on. Stale `python3.12` entries from older
   installs can be removed with the ⊖ button.
3. Relaunch vlow. The Microphone prompt reappears on the first recording.

## Common problems

**The double-tap does nothing.** Run with `VLOW_DEBUG=1`. If hotkey presses
print but no callback fires, your gap is over the 350 ms threshold — tap
faster, or raise `threshold_sec` in `src/vlow/hotkey.py`. If the presses
don't print at all, Accessibility isn't actually active for the running
executable; re-check it as above, then relaunch.

**Stuck in "Recording" forever.** Use the **Stop & Transcribe** menubar item.
If the menu is unresponsive, Quit and restart — the in-flight buffer is lost,
but the audio is still on disk (see
[Recovery](usage.md#recovery--the-last-recording-is-always-on-disk)).

**Empty transcript, or just "Thank you."** Whisper hallucinates that string
on near-silent audio. Confirm the mic is reaching the recorder with
`vlow test` and watch the reported captured duration.

**Paste produces nothing.** Some apps suppress synthesized `Cmd+V`. The
transcript is still on your clipboard — paste it by hand. Or use **Re-paste
Last** from the menubar.

**A model won't download.** Unauthenticated Hugging Face downloads are
rate-limited; see [Configuration](configuration.md#on-device-models) for the
token file.

## The app is wedged

Hotkey dead, menubar icon visible but clicking it does nothing. Before
restarting, capture diagnostics so the cause is findable afterwards:

```sh
# 1. Dump all Python thread stacks into vlow.err
kill -USR1 "$(pgrep -f -- '-m vlow')"

# 2. Read the trail: stack dump, heartbeat lines (every ~5 min: app state,
#    status-item health, whether modifier-key events still arrive), power
#    events, state transitions
tail -150 ~/Library/Logs/vlow/vlow.err

# 3. Restart
launchctl kickstart -k "gui/$UID/com.vlow"
```

A watchdog thread self-heals one variant of this on its own: if the main
runloop stops servicing pings for ~3 minutes while the app is idle, it dumps
stacks and exits so launchd relaunches it.

## Logs

Logs exist when **Start at login** is on — that is what routes vlow's output
to files. They show up in Console.app under "Log Reports".

- `~/Library/Logs/vlow/vlow.err` — startup phases (`[vlow HH:MM:SS] …`) and
  Python stderr
- `~/Library/Logs/vlow/vlow.log` — MLX / AssemblyAI stdout

From a source checkout, `scripts/vlow` wraps the launchd commands:

```bash
vlow status     # launchd state + last log lines
vlow logs       # live tail (Ctrl-C to stop)
vlow restart    # force-restart, picking up new code
vlow stop       # stop until 'vlow start' or the next login
```

## Gatekeeper

The build is ad-hoc signed, so on first launch macOS may say the app "cannot
be verified". Open **System Settings → Privacy & Security**, scroll down and
click **Open Anyway** — or skip quarantine outright:

```bash
xattr -dr com.apple.quarantine /Applications/vlow.app
```
