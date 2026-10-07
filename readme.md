# Waveshare UPS HAT (E) for Home Assistant

Monitor the [Waveshare UPS HAT (E)](https://www.waveshare.com/wiki/UPS_HAT_(E)) in Home Assistant.

UI config flow · proper device with associated entities · clear sensor names · high-level system state

This repository is the actively maintained continuation of the original project by [@mykhailog](https://github.com/mykhailog/hacs_waveshare_ups_hat), with UPS HAT (E) support from [@andriyor](https://github.com/andriyor). **This integration supports the UPS HAT (E) only** (not classic INA219 models).

<img width="420" height="400" alt="image" src="https://github.com/user-attachments/assets/74820614-0d57-45a6-a311-c3653d788e2f" />

## Related repositories

Rule of thumb: HAT on the HA box → use the local integration; HAT on a different Pi → install the remote service on that Pi and the remote integration in Home Assistant.

- [homeassistant_waveshare_ups_hat_e](https://github.com/rbridal/homeassistant_waveshare_ups_hat_e) — Home Assistant integration for a UPS HAT (E) attached directly to the HA host (I2C). **This repo.**
- [ha-ups-hat-e-remote](https://github.com/rbridal/ha-ups-hat-e-remote) — Home Assistant integration that displays a remote UPS HAT (E) over MQTT.
- [ups-hat-e-remote](https://github.com/rbridal/ups-hat-e-remote) — Companion service that runs on the Pi with the HAT, reads I2C, and publishes status over MQTT.

## Installation

### HACS (recommended)

1. **HACS → ⋮ → Custom repositories**
2. Add:
   - **URL:** `https://github.com/rbridal/homeassistant_waveshare_ups_hat_e`
   - **Type:** Integration
3. Search for **Waveshare UPS HAT (E)** and install
4. Restart Home Assistant

### Manual

Copy `custom_components/waveshare_ups_hat/` into your Home Assistant `custom_components` directory and restart.

## Configuration

1. **Settings → Devices & services → Add integration**
2. Search for **Waveshare UPS Hat**
3. Enter I2C bus (usually `1`) and address (default `0x2d`)
4. On the next screen, set the device name (default **UPS**) and optional area

The integration creates one **device** with all sensors and binary sensors attached.

## Entities

| Entity | Description |
|--------|-------------|
| **System state** | High-level status: `OK` · `Recharging` · `On Battery` · `Low Battery` |
| **Battery** | State of charge (%) |
| **Battery pack voltage** | Combined voltage of the series cell pack |
| **Battery charge current** | Current flowing *into* the batteries (A) |
| **Battery discharge current** | Current flowing *out of* the batteries (A) |
| **AC adapter voltage** | Input / VBUS voltage |
| **AC adapter current** | Input / VBUS current |
| **AC adapter power** | Input / VBUS power (W) |
| **AC adapter input status** | MCU input mode: `fast_charging` · `charging` · `discharging` · `idle` |
| **Remaining capacity** | Estimated capacity left (mAh) |
| **Runtime remaining** | Minutes of runtime on battery only |
| **Time to full charge** | Minutes until charged (when applicable) |
| **Battery 1–4 voltage** | Individual cell voltages |
| **Power switch** | Side power switch on / off |
| **Charging** | Batteries are actively charging |

**System state** rules:

- **On Battery** / **Low Battery** — AC adapter absent (VBUS < 1 V) or pack is discharging
- **Recharging** — AC present, charging, and battery < 95%
- **OK** — otherwise (including float/trickle above 95%)

## Enabling I2C

### Home Assistant OS

Follow the [official I2C instructions](https://www.home-assistant.io/common-tasks/os/#enable-i2c) or use the [HassOS I2C Configurator add-on](https://community.home-assistant.io/t/add-on-hassos-i2c-configurator/264167).

### Home Assistant Core / Raspberry Pi OS

```bash
sudo raspi-config   # Interfacing Options → I2C → Yes
sudo apt-get install i2c-tools
sudo addgroup homeassistant i2c
sudo reboot
```

Scan for the device:

```bash
/usr/sbin/i2cdetect -y 1
```

Expected address for UPS HAT (E): **0x2d**.

## Credits

- Original integration by [@mykhailog](https://github.com/mykhailog)
- UPS HAT (E) support by [@andriyor](https://github.com/andriyor)
- Maintained by [@rbridal](https://github.com/rbridal)
- Modernization (config flow, device model, entity redesign, system state) with [Grok](https://grok.x.ai) by xAI

## Built with Grok

This integration was taken from a stale fork to a modern, UI-configured Home Assistant integration in a single late-night session — roughly **two hours of active work** (about 2.5 hours wall-clock with short breaks).

In that time, Grok helped:

- Detach the repo from the old fork network and take ownership
- Replace YAML platform setup with a full **config flow** and **DataUpdateCoordinator**
- Register a real **device** so all entities group correctly in the UI
- Rename every sensor to match what the hardware actually measures
- Split signed battery current into clear **charge** / **discharge** sensors
- Add a **System state** enum (`OK` / `Recharging` / `On Battery` / `Low Battery`) with sensible UPS logic
- Fix entity IDs, friendly names, and config-flow UX
- Focus the integration exclusively on **UPS HAT (E)**

If you maintain hardware integrations (or any Home Assistant custom component) and you’ve been putting off a modernization pass: open a session with Grok, point it at the repo, and ship. The barrier to “make this feel like a first-class HA integration” is much lower than it used to be.

## License

MIT
