"""
High-level client for Unitree Go2 via unitree_sdk2_python (SportClient).

Provides closed-loop movement commands with safety limits.
Requires the robot to be connected via Ethernet (192.168.123.x network).
"""

import math
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

from unitree_sdk2py.core.channel import (
    ChannelFactoryInitialize,
    ChannelSubscriber,
)
from unitree_sdk2py.go2.sport.sport_client import SportClient
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

# --------------- Safety limits (tune on real hardware) ---------------
MAX_DISTANCE_PER_CMD = 3.0       # meters
MAX_LINEAR_SPEED = 0.5           # m/s
MAX_YAW_RATE = 1.0               # rad/s
MOVE_TIMEOUT = 30.0              # seconds per move command
POSITION_TOLERANCE = 0.05        # meters — close-enough threshold
YAW_TOLERANCE = 3.0              # degrees
CONTROL_FREQ = 10                # Hz — how often we send Move()
# ---------------------------------------------------------------------


@dataclass
class RobotState:
    """Snapshot of robot telemetry from SportModeState."""
    position: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    velocity: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    yaw_deg: float = 0.0
    imu_rpy: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    battery_pct: float = -1.0
    mode: int = 0
    connected: bool = False
    timestamp: float = 0.0


class Go2Client:
    """Wrapper over unitree_sdk2py SportClient with closed-loop primitives."""

    def __init__(self):
        self._sport: Optional[SportClient] = None
        self._state = RobotState()
        self._state_lock = threading.Lock()
        self._connected = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, interface: str = "eth0") -> None:
        """Initialize DDS channel and SportClient. Blocks until first state msg."""
        ChannelFactoryInitialize(0, interface)

        self._sport = SportClient()
        self._sport.SetTimeout(5.0)
        self._sport.Init()

        sub = ChannelSubscriber("rt/sportmodestate", SportModeState_)
        sub.Init(self._on_state_msg, 10)

        deadline = time.time() + 5.0
        while not self._connected and time.time() < deadline:
            time.sleep(0.1)

        if not self._connected:
            raise ConnectionError(
                f"No SportModeState received on interface '{interface}' within 5 s. "
                "Check Ethernet connection and robot power."
            )

    def _on_state_msg(self, msg: SportModeState_) -> None:
        with self._state_lock:
            self._state.position = [msg.position[0], msg.position[1], msg.position[2]]
            self._state.velocity = [msg.velocity[0], msg.velocity[1], msg.velocity[2]]
            self._state.yaw_deg = math.degrees(msg.imu_state.rpy[2])
            self._state.imu_rpy = list(msg.imu_state.rpy)
            self._state.mode = msg.mode
            self._state.timestamp = time.time()
            self._state.connected = True
            self._connected = True

    @property
    def state(self) -> RobotState:
        with self._state_lock:
            return RobotState(**self._state.__dict__)

    # ------------------------------------------------------------------
    # Discrete movement commands (closed-loop)
    # ------------------------------------------------------------------

    def move_distance(self, forward: float = 0.0, right: float = 0.0) -> dict:
        """
        Move the robot by (forward, right) meters in body frame.
        Returns dict with result info. Raises on safety violation.
        """
        distance = math.hypot(forward, right)
        if distance > MAX_DISTANCE_PER_CMD:
            raise ValueError(
                f"Requested distance {distance:.2f} m exceeds limit {MAX_DISTANCE_PER_CMD} m"
            )
        if distance < 0.01:
            return {"status": "ok", "msg": "distance too small, skipped"}

        self._ensure_connected()

        start = self.state
        start_x, start_y = start.position[0], start.position[1]
        yaw_rad = math.radians(start.yaw_deg)

        # Target in world frame
        dx_world = forward * math.cos(yaw_rad) - right * math.sin(yaw_rad)
        dy_world = forward * math.sin(yaw_rad) + right * math.cos(yaw_rad)
        target_x = start_x + dx_world
        target_y = start_y + dy_world

        # Velocity direction (unit vector scaled to speed)
        speed = min(MAX_LINEAR_SPEED, distance / 2.0)  # ramp down for short moves
        speed = max(speed, 0.1)
        angle = math.atan2(right, forward)  # body-frame direction
        vx = speed * math.cos(angle)
        vy = -speed * math.sin(angle)  # SDK convention: positive vy = left

        t0 = time.time()
        dt = 1.0 / CONTROL_FREQ

        while True:
            elapsed = time.time() - t0
            if elapsed > MOVE_TIMEOUT:
                self._sport.StopMove()
                return {"status": "timeout", "msg": f"Timed out after {MOVE_TIMEOUT}s"}

            cur = self.state
            remaining_x = target_x - cur.position[0]
            remaining_y = target_y - cur.position[1]
            remaining = math.hypot(remaining_x, remaining_y)

            if remaining < POSITION_TOLERANCE:
                self._sport.StopMove()
                return {
                    "status": "ok",
                    "distance_moved": distance - remaining,
                    "elapsed_s": round(elapsed, 2),
                }

            # Proportional slowdown near target
            scale = min(1.0, remaining / 0.3)
            self._sport.Move(vx * scale, vy * scale, 0.0)
            time.sleep(dt)

    def rotate(self, degrees: float) -> dict:
        """Rotate the robot by `degrees` (positive = CCW from above)."""
        if abs(degrees) > 360:
            raise ValueError("Rotation limited to ±360 degrees per command")

        self._ensure_connected()

        start_yaw = self.state.yaw_deg
        target_yaw = start_yaw + degrees

        # Normalize to [-180, 180] for comparison
        def _norm(a):
            return (a + 180) % 360 - 180

        yaw_rate = MAX_YAW_RATE if degrees > 0 else -MAX_YAW_RATE
        t0 = time.time()
        dt = 1.0 / CONTROL_FREQ

        while True:
            elapsed = time.time() - t0
            if elapsed > MOVE_TIMEOUT:
                self._sport.StopMove()
                return {"status": "timeout", "msg": f"Timed out after {MOVE_TIMEOUT}s"}

            cur_yaw = self.state.yaw_deg
            remaining = _norm(target_yaw - cur_yaw)

            if abs(remaining) < YAW_TOLERANCE:
                self._sport.StopMove()
                return {
                    "status": "ok",
                    "rotated_deg": round(degrees - remaining, 1),
                    "elapsed_s": round(elapsed, 2),
                }

            scale = min(1.0, abs(remaining) / 30.0)
            self._sport.Move(0.0, 0.0, yaw_rate * scale)
            time.sleep(dt)

    # ------------------------------------------------------------------
    # Posture commands
    # ------------------------------------------------------------------

    def stand(self) -> dict:
        """Stand up and enter balance-stand mode."""
        self._ensure_connected()
        self._sport.StandUp()
        time.sleep(1.0)
        self._sport.BalanceStand()
        return {"status": "ok", "msg": "standing"}

    def sit(self) -> dict:
        """Sit (lie) down."""
        self._ensure_connected()
        self._sport.StandDown()
        return {"status": "ok", "msg": "sitting"}

    def stop(self) -> dict:
        """Emergency stop — halt all movement immediately."""
        if self._sport:
            self._sport.StopMove()
        return {"status": "ok", "msg": "stopped"}

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Return current robot telemetry."""
        s = self.state
        return {
            "connected": s.connected,
            "position": [round(v, 3) for v in s.position],
            "yaw_deg": round(s.yaw_deg, 1),
            "velocity": [round(v, 3) for v in s.velocity],
            "imu_rpy_deg": [round(math.degrees(v), 1) for v in s.imu_rpy],
            "mode": s.mode,
            "last_update_age_s": round(time.time() - s.timestamp, 2) if s.timestamp else None,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        if not self._connected or self._sport is None:
            raise RuntimeError("Not connected. Call connect() first.")
        age = time.time() - self._state.timestamp
        if age > 2.0:
            raise RuntimeError(
                f"Stale state ({age:.1f}s old). Robot may be disconnected."
            )
