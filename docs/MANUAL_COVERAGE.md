# SmarTouch manual: what Home Assistant can do

This maps every feature in the ACC SmarTouch Digital manuals to what this
integration offers. It was checked against two manuals:

* **User Manual**: SmarTouch Digital User Manual, Rev. 05/2017-ACC (KP-2020 panel, WiFi section).
* **Programming Manual**: SmarTouch Digital Series 1000 & 2000 User & Programming Manual.

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
| Time of day: set it (hold TIME) | User 5; Prog 6 | `time.spa_spa_clock` (set), **Sync spa clock** button, optional daily sync in the integration's options | Unverified: written in the app's format, not yet seen applied |
| Time of day shown each minute | Prog 6 | `time.spa_spa_clock` reads it from the display | Unverified: not seen yet, the clock may never have been set |
| JETS key: low, high, off (dual speed) or on, off (single speed) | User 6-7; Prog 7-9 | **Jets** select (Off / Lo / Hi) from the Jets Lo/Hi lights, **Jets key** button | Unverified |
| AUX key: second pump, or two pumps cycling P1, P1+2, P2, off | User 6; Prog 8-9 | **Jets 2** select (Off / Lo / Hi / Lo + Hi) from the Jets 2 lights, **Aux key** button | Unverified |
| AIR key: air blower on/off (or a single-speed second pump) | User 6-7; Prog 8-9 | **Air** select from the Air Lo/Hi lights, **Air key** button | Unverified |
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

## Not reachable from Home Assistant

These need key combinations (SET+DOWN, UP+DOWN, SET+UP) or the UP and DOWN
keys, and the SmarTouch app has no Bluetooth codes for them. Set them on the
spa-side panel.

| Manual feature | Pages |
|---|---|
| Filtration periods FP1-FP4 (start times and durations FP1d-FP4d) | User 13-14; Prog 13-14 |
| Silence period SIL / SILd | User 14; Prog 14 |
| Cool-down length CLDN, economy cycle ECL, channel clear CHCL, user time-out UTO, post-use filtration PUF | User 15; Prog 15 |
| Temperature calibration CALB | User 16; Prog 16 |
| User options U1-U8 (economy vs. auto, low pump on demand, auto filtration, user timer, clock display, °F/°C) | Prog 17-18 |
| Protected options P1-P8 (pump types, low power, light mode, blower) | User 19; Prog 19-20 |
| Diagnostic values D1-D8 | Prog 20 |
| Invert the display (SET+UP) | User 6-7; Prog 10 |
| WiFi board setup | User 21. The app's WiFi mode is a cloud relay (docs/PROTOCOL.md), so no WiFi transport is built. |
