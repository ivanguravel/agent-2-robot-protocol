---
name: go2-control
description: >-
  Control a Unitree Go2 robot with natural-language movement commands.
  Use when the user says: пройди, шаг, шагов, вперёд, назад, влево, вправо,
  повернись, развернись, робот, Go2, сядь, встань, стоп, остановись,
  симуляция, эмулятор, Gazebo, walk, step, rotate, turn, sit, stand, stop.
---

# Go2 Robot Control

Execute discrete movement commands on a physical Unitree Go2 via the CLI at
`go2_real/go2_cli.py`.

## Step Convention

**1 step = 0.3 meters.**

When the user says "N шагов/steps", multiply by 0.3 to get meters.

## Command Mapping

| User says (examples) | CLI command |
|---------------------|-------------|
| пройди 3 шага прямо | `python3 go2_real/go2_cli.py walk --forward 0.9` |
| 2 шага назад | `python3 go2_real/go2_cli.py walk --forward -0.6` |
| 1 шаг вправо | `python3 go2_real/go2_cli.py walk --right 0.3` |
| шаг влево | `python3 go2_real/go2_cli.py walk --right -0.3` |
| пройди 1 метр вперёд | `python3 go2_real/go2_cli.py walk --forward 1.0` |
| повернись направо на 90 | `python3 go2_real/go2_cli.py rotate -90` |
| повернись налево | `python3 go2_real/go2_cli.py rotate 90` |
| развернись | `python3 go2_real/go2_cli.py rotate 180` |
| встань | `python3 go2_real/go2_cli.py stand` |
| сядь | `python3 go2_real/go2_cli.py sit` |
| стоп / остановись | `python3 go2_real/go2_cli.py stop` |
| статус | `python3 go2_real/go2_cli.py status` |

Rotation sign: positive = counter-clockwise (left), negative = clockwise (right).

## Compound Commands

When the user gives a compound instruction like "пройди 3 шага прямо и 1 вправо",
execute commands **sequentially**, checking the exit code after each:

```bash
python3 go2_real/go2_cli.py walk --forward 0.9
# check exit code == 0
python3 go2_real/go2_cli.py walk --right 0.3
```

Do NOT combine forward and right in a single `walk` call unless the user
explicitly asks for diagonal movement (e.g., "иди по диагонали").

## Safety Protocol

1. **Before the first movement** in a session, run `status` to verify:
   - `"connected": true`
   - State age < 2 seconds
   - If status fails — report to user, do NOT attempt movement.

2. **Execute commands one at a time.** Wait for JSON response and exit code 0.

3. **On any error** (exit code 1, timeout, or exception):
   - Immediately run `python3 go2_real/go2_cli.py stop`
   - Report the error to the user.
   - Do NOT continue the remaining sequence.

4. **Distance limit**: never exceed 3.0 m in a single walk command.
   If the user asks for more, split into multiple commands of <= 3 m.

5. **Ambiguity**: if the command is unclear (e.g., "иди туда"), ask the user
   to clarify direction and distance before executing.

## Simulation Mode

When the user mentions "симуляция", "эмулятор", "Gazebo", or the Docker
simulator is known to be running, add `--sim` to all CLI calls:

```bash
python3 go2_real/go2_cli.py --sim walk --forward 0.9
python3 go2_real/go2_cli.py --sim rotate -90
python3 go2_real/go2_cli.py --sim status
```

The simulated robot moves slower (~0.035 m/s). Commands take longer but
the interface is identical. The first movement command automatically
activates TROT mode on the simulated robot.

If the user doesn't specify real/sim but a Docker simulator container
is likely running (e.g., they mentioned it earlier in the conversation),
use `--sim`.

## Working Directory

Always run the CLI from the repository root:

```bash
cd /Users/ivanzhuravel/Downloads/go2_ros2_sim_py
python3 go2_real/go2_cli.py <command>
```

## Environment

**Real robot:**
```bash
export GO2_IFACE=enp3s0
# or pass --iface enp3s0
```

**Simulation:**
```bash
export GO2_MODE=sim
# or pass --sim
# Container name defaults to "simulator-gui", override with:
export GO2_CONTAINER=simulator-gui
# or pass --container simulator-gui
```
