# SmarTouch manual: what Home Assistant can do

This maps every feature in the ACC SmarTouch Digital manuals to what this
integration offers. It was checked against two manuals:

* **User Manual**: SmarTouch Digital User Manual, Rev. 05/2017-ACC (KP-2020 panel, WiFi section).
* **Programming Manual**: SmarTouch Digital Series 1000 & 2000 User & Programming Manual.

**Air and Jets 2 may be swapped.** The app's two spa keypad layouts disagree
on whether the `a0` key sits under the Air lights or the Jets 2 lights
(docs/PROTOCOL.md, "Buttons"). The selects use the layout the app loads; a
press test on the spa settles it.

The integration can only send what the SmarTouch app sends over Bluetooth
(docs/PROTOCOL.md): one press of LITE, JETS, AIR, AUX or SET, a set point,
and the time of day. It cannot press two keys together or use the UP and
DOWN keys, so **nothing in the programming menus is reachable**. Those
settings stay on the spa-side panel.

"Unverified" means the integration follows the app's code and the manual,
but it has not yet been seen working on the owner's spa.

## Everyday use

| Manual feature | Pages | Home Assistant | Status |
|---|---|---|---|
| Set temperature, 40-104 °F (or the matching °C) | User 4; Prog 5, 10 | `climate.spa` target temperature | Unverified: the write is the app's, the display has not yet shown a set point |
| Water temperature display | User 3-4 | `climate.spa` current temperature, `sensor.spa_water_temperature` | Confirmed (98 °F decoded on 2026-11-02) |
| °F or °C display (option U6) | Prog 18 | Follows the unit the display shows | Unverified for °C |
| Time of day: set it (hold TIME) | User 5; Prog 6 | **Clock** time entity (set), **Sync clock** button, optional daily sync in the integration's options | Unverified: written in the app's format, not yet seen applied |
| Time of day shown each minute | Prog 6 | the **Clock** entity reads it from the display | Unverified: not seen yet, the clock may never have been set |
| JETS key: low, high, off (dual speed) or on, off (single speed) | User 6-7; Prog 7-9 | **Jets 1**: a switch for one speed, a select (Off / Low / High) for two; **Jets key** button | Confirmed as on/off on the owner's spa |
| AUX key: second pump, or two pumps cycling P1, P1+2, P2, off | User 6; Prog 8-9 | **Jets 2**: a switch, Off / Low / High, or Off / Jets A / Jets B / Both for two pumps; **Aux key** button | Confirmed with two pumps on the owner's spa |
| AIR key: air blower on/off (or a single-speed second pump) | User 6-7; Prog 8-9 | **Air** switch when a blower is fitted; **Air key** button | Toggles the Air Hi light; no blower on the owner's spa |
| Equipment (P1, P2, P6, P7, P8) | Prog 19-20 | Integration options **Jets 1**, **Jets 2**, **Air blower**; Auto reads them from the options menu | Confirmed: the owner's spa read P2 1, P8 1 |
| LITE key: light on/off, or light, light + accessory, off (option P4) | Prog 8-9, 19 | `light.spa_light` | Confirmed for on/off; the 3-function mode would need the light key pressed twice, which the light entity does not do |
| SET key: done using the spa (all off, post-use filtration) | User 4; Prog 5, 11 | **Set key (done using spa)** button | Unverified |
| SET clears a high-limit (HLoH) error once fixed | Prog 11, 21 | Same button | Unverified |
| User timer: everything off after 20 min (UTO) | User 5; Prog 15 | Nothing to do: the selects and light follow the lights when it happens | — |
| Cool-down: low jets run 30-60 s after the heater stops | User 5; Prog 15 | Shows as the Jets low light; the Jets select may refuse Off while it runs | — |
| Heater holds the low pump on | Prog 7 | The Jets select stops with an error instead of pressing forever | Tested in simulation |

## Status and indicator lights

| Manual feature | Pages | Home Assistant | Status |
|---|---|---|---|
| Economy mode, display shows ECON | User 5; Prog 5 | `binary_sensor.spa_economy_mode`, `sensor.spa_status` = Economy | Confirmed (ECon seen 2026-11-02) |
| Heating light | panel | `binary_sensor.spa_heating`, climate `hvac_action` | Unverified |
| Filtering light, post-use filtration | Prog 5, 15 | `binary_sensor.spa_filtering` | Unverified |
| OverHeat light | panel | `binary_sensor.spa_overheat`, also turns on **Problem** | Unverified |
| Program/Edit light | panel | `binary_sensor.spa_edit_indicator` (diagnostic) | Unverified |
| AM light | panel | `binary_sensor.spa_am_indicator` (diagnostic); used to read the clock | Unverified |
| Jets, Jets 2 and Air Lo/Hi lights | panel | the six Lo/Hi binary sensors, and the selects | Unverified |
| Light | panel | `light.spa_light` state | Confirmed |
| Programming menu open on the panel (FP1 ... CANC, U/P/D options) | User 12-16; Prog 12-20 | `sensor.spa_status` = Programming | Unverified |

## Error codes

All of these set `sensor.spa_status` to the error, with a short explanation
in its `description` attribute, and turn on `binary_sensor.spa_problem`.
None has been seen on the owner's spa, so all are Unverified.

| Code | Meaning (paraphrased) | Pages |
|---|---|---|
| CoLd | Water below 40 °F; the low pump runs until it is above 45 °F | User 25; Prog 21 |
| OH | Water above 108 °F | User 25; Prog 21 |
| HLoH (HLer) | High-limit sensor tripped or disconnected; press SET once fixed | User 25; Prog 21 |
| SEoP | Temperature sensor open or disconnected; heater off | User 25; Prog 22 |
| SESH | Temperature sensor shorted; heater off | User 25; Prog 22 |
| PSoC, PSoL, PSoH | No water pressure with the circulation, low or high pump on | User 10, 25; Prog 22 |
| ToE | Controller time-out; everything off | Prog 22 |

## Programming menus

The panel opens its menus only with two keys pressed together (SET+DOWN for
parameters, UP+DOWN for options), and the app's Bluetooth codes are single
taps. Home Assistant cannot open a menu, but it follows one you open and can
take over once it is open:

* **Capture.** While you scroll a menu at the panel, every value it shows is
  recorded and kept across restarts. U and P values show in the list; a
  parameter's value shows after SET on it. A session's edits count only if
  it ends with SET on SEnd.
* **Takeover.** Change the settings entities in Home Assistant (they show
  the value that will be written), open the matching menu at the panel, and
  press **Apply settings**. It steps with UP/DOWN to each changed item, sets
  it, and saves with SEnd, checking the display after every press. It never
  writes P options or the reserved U7/U8. The UP/DOWN codes have not been
  seen in use before, so the first takeover is also their first test.

| Manual feature | Pages | Home Assistant | Status |
|---|---|---|---|
| Filtration start times FP1-FP4 | User 13-14; Prog 13-14 | time entities, settable | Menu items confirmed; values not seen yet |
| Filtration durations FP1d-FP4d | User 14; Prog 14 | number entities, 0-240 min | Same |
| CLdn, ECL, CHCL, Uto, PUF | User 15; Prog 15 | number entities | Same |
| U1-U6 user options | Prog 17-18 | switches, settable | Values confirmed (all 0) |
| U7, U8 (reserved) | Prog 18 | read-only binary sensors | Values confirmed |
| P1-P8 protected options | User 19; Prog 19-20 | read-only binary sensors; they also shape the jets entities | Values confirmed |
| d1-d8 diagnostic values | Prog 20 | read-only sensors, disabled by default | Labels confirmed; values show after SET |
| Silence period SIL/SILd, calibration CALb | User 14, 16; Prog 14, 16 | none | Not in this firmware's menu |
| Invert the display (SET+UP) | User 6-7; Prog 10 | none | Needs two keys at once |
