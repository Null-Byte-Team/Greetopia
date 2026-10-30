# Original and legacy firmware (reference only)

| File | Origin |
|---|---|
| `sensor_node_original.ino` | Older sensor-node sketch (DRY 3000 / WET 1200, no probe power pins). |
| `plant_node_firmware_newer_original.ino` | Newer sensor-node sketch supplied by the project owner (DRY 4095 / WET 1500, probe power pins 25/27/14, calibration mode, 16-sample averaging). **v2 is based on this one.** |
| `esp32_cam_original.ino` | Original camera sketch (identical to the camera file supplied by the owner). |
| `sensor_node_greetopia_ready.ino`, `esp32_cam_greetopia_ready.ino` | Earlier "ready" variants. The sensor one is **deprecated and unsafe** (see its header). |
| `software_specification_original.html` | The original software specification. |

These files are not modified. Use `firmware/sensor_node` and `firmware/camera_node` (v2).
The two sensor sketches are *different programs*; do not assume the older one reflects the hardware you actually flashed.
