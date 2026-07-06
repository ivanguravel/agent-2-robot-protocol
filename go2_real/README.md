# go2_real — Unitree Go2 Real Robot Control

Control a physical Unitree Go2 robot via `unitree_sdk2_python` (SportClient high-level API).
This package has **no ROS 2 dependency** — it works standalone with just Python 3.8+.

## Prerequisites

- **Unitree Go2 EDU** (or Pro with sport-mode access)
- Ethernet cable between your PC and the robot
- PC configured on the `192.168.123.x` subnet (robot is at `192.168.123.161`)

## Network Setup

```bash
# Example: configure your Ethernet adapter (replace eth0 with your interface)
sudo ip addr add 192.168.123.100/24 dev eth0
sudo ip link set eth0 up

# Verify connectivity
ping 192.168.123.161
```

## Installation

```bash
cd go2_real
pip install -r requirements.txt
```

The SDK depends on CycloneDDS Python bindings. If installation fails, you may need to build
CycloneDDS from source and set `CYCLONEDDS_HOME`:

```bash
git clone https://github.com/eclipse-cyclonedds/cyclonedds.git
cd cyclonedds && mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=/opt/cyclonedds
make -j$(nproc) && sudo make install
export CYCLONEDDS_HOME=/opt/cyclonedds
pip install cyclonedds
```

## Usage

### CLI (designed for Cursor agent integration)

```bash
# Check robot status
python3 go2_cli.py status

# Stand up
python3 go2_cli.py stand

# Walk forward 0.9 m, then right 0.3 m
python3 go2_cli.py walk --forward 0.9
python3 go2_cli.py walk --right 0.3

# Rotate 90 degrees counter-clockwise
python3 go2_cli.py rotate 90

# Sit down
python3 go2_cli.py sit

# Emergency stop
python3 go2_cli.py stop
```

### Dry-run mode (no robot required)

```bash
python3 go2_cli.py --dry-run walk --forward 1.0
# Outputs JSON plan without connecting
```

### Specify network interface

```bash
python3 go2_cli.py --iface enp3s0 status
# Or set environment variable:
export GO2_IFACE=enp3s0
```

### Python API

```python
from go2_client import Go2Client

client = Go2Client()
client.connect(interface="eth0")

print(client.status())
client.stand()
client.move_distance(forward=1.0)
client.rotate(90)
client.sit()
```

## Safety Limits

Configured at the top of `go2_client.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| MAX_DISTANCE_PER_CMD | 3.0 m | Max distance in a single walk command |
| MAX_LINEAR_SPEED | 0.5 m/s | Velocity cap |
| MAX_YAW_RATE | 1.0 rad/s | Rotation speed cap |
| MOVE_TIMEOUT | 30 s | Abort if target not reached |
| POSITION_TOLERANCE | 0.05 m | Close-enough threshold |
| YAW_TOLERANCE | 3.0 deg | Rotation close-enough threshold |

Adjust these after testing on your robot.

## Troubleshooting

- **"No SportModeState received"** — check Ethernet cable, IP config, robot power. Robot must be powered on and in sport mode.
- **"Stale state"** — the robot stopped sending telemetry. Restart the robot or check cable.
- **SDK install fails** — ensure you have Python 3.8+, cmake, and a C++ compiler for CycloneDDS.
