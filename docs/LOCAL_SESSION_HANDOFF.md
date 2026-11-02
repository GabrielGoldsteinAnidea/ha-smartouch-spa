# Handoff: finish the SmarTouch Spa integration in a local session

Paste everything below the line into a Claude Code session running on the
Windows PC. Start it in the restored `ha-smartouch-spa` folder.

---

You are continuing work on `ha-smartouch-spa`. It is a Home Assistant custom
integration, plus reverse-engineering tooling, for a hot tub with an ACC
(Applied Computer Controls) SmarTouch Digital control and a BWF-200
WiFi/Bluetooth module. The phone app is "SmarTouch Digital". The earlier
cloud session could not reach the phone or create the GitHub repo, so this
session finishes the job.

**My rules for this work:** Cite what you researched. State every assumption
explicitly. This is engineering work, so don't guess. If something can't be
verified, say so instead of filling the gap.

## Read first (do not re-derive)

- `README.md`: the architecture and the reasons behind it.
- `docs/PROTOCOL.md`: the facts that are known, each with a source, and a table of unknowns. Your job is to fill in that table.
- `docs/REVERSE_ENGINEERING.md`: the capture procedure and tool usage.
- `custom_components/smartouch_spa/spa_core/profile.py`: the only place protocol facts go. It defaults to discovery mode.
- `custom_components/smartouch_spa/client.py`: the BLE client. Its `press()` and `ensure_connected()` are where a codec or handshake would go if captures need one.

## Step 1: Publish the repo

The folder was cloned from a git bundle. If `origin` still points at the
bundle file, remove it first, then create the repo:

```bash
git remote remove origin
```

```bash
gh repo create GabrielGoldsteinAnidea/ha-smartouch-spa --public --source . --push
```

Run `gh auth status` first. If `gh` isn't logged in, ask me to run `gh auth login`.
Confirm that the CI workflow (`.github/workflows/ci.yml`: ruff, pytest,
hassfest, HACS) runs, and fix anything it reports.

## Step 2: Tooling check

Shell scripts in `tools/adb/` are bash; on Windows run them with Git Bash
(`"C:\Program Files\Git\bin\bash.exe" tools/adb/find_package.sh`).
Check `adb version`, `python --version`, and `java -version`. jadx is needed
for decompiling; install it if it's missing (https://github.com/skylot/jadx/releases).
Ask me before installing anything system-wide.

Then run `adb devices`. If the phone isn't listed, ask me to enable USB
debugging and accept the prompt on the phone.

## Step 3: Static analysis (no spa needed)

1. Run `tools/adb/find_package.sh`. Confirm the real package name; the docs only have a third-party report of `com.mltech.agi.accslv2a`. Record the version and the permissions.
2. Run `tools/adb/pull_apk.sh`, then `tools/adb/decompile.sh captures/apk/base.apk`.
3. Read `captures/findings/*` and the relevant decompiled classes. From the code, determine:
   - the GATT service, notify and write UUIDs, and the write type;
   - how a button command is built (header, length, checksum or counter, press/release pair);
   - whether the PIN is used on each connection, and how;
   - how received bytes become the display (frame layout, digit offsets, segment bit order, indicator LEDs);
   - whether WiFi mode is LAN or cloud (hosts, ports, protocol).

   If the app is Flutter, React Native or Xamarin (the script reports this), stop and tell me which. The approach changes.
4. Write each finding into `docs/PROTOCOL.md`, citing the class, method and file it came from.

## Step 4: Capture live traffic (the phone must be in BLE range of the spa)

The phone has to stay connected to the PC by USB, so the laptop needs to be
near the spa. Confirm with me that this is set up before starting.

- Follow `docs/REVERSE_ENGINEERING.md` §3. Do one action per capture: `idle`, `light`, `temp_up`, `temp_down`, `filter`, `jets`.
- You can drive the app yourself with `adb exec-out screencap -p > screen.png` (look at it) and `adb shell input tap X Y`, or ask me to tap. Either way, log the wall-clock time of each action in `captures/<label>.notes`.
- Analyze each capture with `tools/analysis/btsnoop_att.py` (`--writes`, `--unique`). Cross-check every finding against the static analysis from Step 3. A fact counts as confirmed only when two sources agree, or when a replay test succeeds (Step 5).
- `captures/` is git-ignored because it may contain the PIN and MAC addresses. Never commit or paste its raw contents anywhere public.

## Step 5: Confirm by replay

Use either Python with `bleak` on the PC, or the integration in Home Assistant
(discovery mode plus the `smartouch_spa.send_raw` service). Replay one
observed button payload, such as Light, and confirm the spa responds. Close the
phone app first, because the module probably accepts only one BLE connection.

**Safety:** this controls a heater and pumps. Only send payloads you have
observed the real app sending. Do not fuzz, and do not send guessed bytes.
For temperature tests, stay within the normal range (for example 98–102 °F).

## Step 6: Encode the findings

1. Put the confirmed values as defaults in `spa_core/profile.py`.
2. If commands aren't static payloads (they have a counter, checksum or handshake), add a codec in `spa_core/` with unit tests built from real captured frames. Redact the PIN and MAC from the test fixtures.
3. Revisit the assumptions listed in `docs/PROTOCOL.md` ("Assumptions currently built into the integration"). Update the code wherever captures prove an assumption wrong. For example, if indicator LEDs show light and filter state, add `light` and `switch` entities that use that state.
4. If WiFi mode is a usable LAN protocol, propose adding a WiFi transport and ask me before building it.
5. Run the checks:

   ```bash
   pip install homeassistant pytest pytest-asyncio ruff
   ```

   ```bash
   ruff check . && ruff format --check . && pytest
   ```

   All of them must pass.

## Step 7: Test in Home Assistant

I have a Home Assistant MCP connector. Use it to check the integration's
state, logs and entities after I install it. You can install it by HACS custom
repository or by copying `custom_components/smartouch_spa` into the config
directory; ask me which. Verify all of these:

- water temperature matches the spa panel;
- setting the target temperature reaches it and the panel agrees;
- the Light and Filter buttons work.

Report any mismatch with evidence.

## Step 8: Finish

Commit with clear messages and push to `main`, or open a PR if I ask for one.
Then give me a summary that separates what was confirmed (with its evidence)
from what is still assumed or unknown.
