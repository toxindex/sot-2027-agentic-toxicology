# Recording the backup video

A 3 to 5 minute screen recording that stands in for the live demo if the
conference network, PubChem or GitHub is having a bad day. Record it once, keep
it on the laptop, and never depend on a network during the talk.

Two routes. Pick one.

* **asciinema** for a terminal-only recording: tiny, sharp text at any
  projector resolution, and the commands can be copied out of it afterwards.
  This is the better choice if the demo stays in the terminal.
* **OBS Studio** for anything that also shows the notebook or a browser tab.

## Before you record, both routes

Warm everything, so the recording shows the demo and not a progress bar:

```bash
cd ~/git/toxindex/sot-2027-agentic-toxicology
uv sync --extra notebook      # environment in place
uv run demo >/dev/null        # checkpoint and ICE tables cached
uv run pytest -q              # confirm the machine is in a good state
```

Then set the stage:

* Terminal font at 18 to 22 pt. Check it is legible from the back of a room by
  standing up and walking away from the screen.
* Window about 110 columns by 32 rows. Narrower than that and the provenance
  lines wrap badly; wider and the text is too small on a projector.
* Dark background, light text. Projectors wash out light backgrounds.
* Turn off notifications, Slack, mail and any status bar with an email subject
  or a client name in it.
* Clear the scroll buffer so nothing from before the recording is visible.
* Decide not to narrate from the terminal: record a clean screen and talk over
  it live, or record audio in a second pass. Live narration over a recording is
  easier to keep in sync than it sounds.

## Route A: asciinema

```bash
# once
sudo apt install asciinema        # or: uv tool install asciinema

asciinema rec sot2027-demo.cast --idle-time-limit 2 --cols 110 --rows 32
#   ... run the script below ...
exit                              # or ctrl-D, which stops the recording

asciinema play sot2027-demo.cast  # watch it back before you trust it
```

`--idle-time-limit 2` collapses any pause longer than two seconds, so thinking
time between commands does not cost video length.

To hand it to someone or embed it in a deck without an upload, convert it:

```bash
uv tool run --from asciinema-agg agg sot2027-demo.cast sot2027-demo.gif
```

Do not run `asciinema upload` or `asciinema auth`: that publishes the cast to a
public server. Keep the `.cast` file local.

## Route B: OBS Studio

* Source: **Screen Capture**, cropped to the terminal window, or **Window
  Capture** on the terminal so a stray notification cannot appear in frame.
* Output: 1920x1080, 30 fps, MP4, CRF about 20. Bigger resolutions buy nothing
  for terminal text.
* Audio: capture the microphone on a separate track if you plan to narrate, so
  the audio can be redone without re-recording the screen.
* Start recording, run the script below, stop recording, and **watch the whole
  file back** before deleting anything.

## The script, with timings

Total about 4 minutes. The commands are the whole of it; everything else is what
to say and where to point.

**0:00 to 0:25 — what is on screen.** Show the repository, nothing running yet.

```bash
ls
sed -n '1,20p' README.md
```

Say: three tools, public data, a public model, and an agent that cites
everything. One command runs it. No API key.

**0:25 to 1:05 — the data is addressable.** Show that the data slice is pinned,
not downloaded on trust.

```bash
uv run python -c "
from agentic_tox import kg
print(len(kg.brick_listing()), 'tables in the brick')
for name, pin in kg.TABLES.items(): print(name, pin['md5'], pin['bytes'])
"
```

Say: this is a public BioBricks brick of the NICEATM Integrated Chemical
Environment. Each table is addressed by its MD5, so the demo verifies the bytes
instead of trusting the host. Total for this demo: under a megabyte.

**1:05 to 1:35 — the model is public and runs on this CPU.**

```bash
uv run python -c "
from agentic_tox import model
print(model.REPO, 'commit', model.COMMIT[:12])
print(f'{model.PARAMETERS:,} parameters, weights sha256 {model.ARTIFACTS[0][\"sha256\"][:16]}...')
for e in model.ENDPOINTS.values(): print(f'  {e.index:5d} [{e.catalog_source}] {e.title}')
"
```

Say: MIT licensed code and weights, 59 million parameters, 6,647 property heads,
of which this demo pins five by index and by stable identifier. CPU only, about
a tenth of a second per prediction.

**1:35 to 3:10 — the whole demo, one command.** This is the heart of it. Let it
run and scroll; do not cut it.

```bash
uv run demo
```

Point at, in this order:

1. step 1, the structure, and that PubChem is cited for it;
2. step 3, the measured ICE records, and that the bacterial mutagenicity record
   is `Weakly Positive; Negative; Negative`, three study calls in one row;
3. step 4, the three model heads disagreeing (0.210, 0.773, 0.112), and say that
   this is the useful part, not a flaw: they are three different public assay
   labels, and an agent that averaged them and stopped would be hiding the only
   thing worth arguing about;
4. the ANSWER block, and the last line of the output: every fact traceable to a
   dataset digest, a weights hash or an API request, with a timestamp.

**3:10 to 3:40 — the trace is machine-readable.**

```bash
uv run demo --json | head -40
```

Say: this is what you attach to a report, or hand to a reviewer who wants to
check the agent rather than trust it.

**3:40 to 4:10 — the limits, on screen.**

```bash
sed -n '/^## What this shows/,/^## Troubleshooting/p' README.md
```

Say the "does not show" list out loud. It is the part of the talk that a
regulator in the audience will remember.

**Optional tail, 30 s — the notebook.** Only if the recording is already under
four minutes.

```bash
uv run jupyter lab demo.ipynb     # then run the cells top to bottom
```

## After recording

* Watch it back at full screen. If text is unreadable at 50 per cent zoom, the
  font was too small.
* Check nothing confidential is in frame: no client names, no internal
  hostnames, no mail, no Slack, no shell prompt showing a private path you would
  rather not show.
* Keep the file on the presenting laptop and on one other disk. Do not rely on
  retrieving it from the network during the session.
* Name it with the date, for example `sot2027-demo-2027-03-15.mp4`, so there is
  no doubt which recording matches the current state of the repository.
* If the repository changes after recording, either re-record or say on the
  slide which commit the video shows.
