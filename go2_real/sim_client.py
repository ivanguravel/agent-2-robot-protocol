"""
Simulation backend for Go2 CLI — controls the robot in Gazebo via docker exec + ros2 commands.

Same interface as Go2Client, so the CLI can switch between real and sim transparently.
"""

import json
import math
import subprocess
import time
from typing import Optional

# --------------- Simulation parameters (tune to match sim controller) ---------------
SIM_SPEED = 0.035            # m/s — max linear speed of sim robot (from cmd_vel_pub.py)
SIM_YAW_RATE = 0.5          # rad/s — max yaw rate in sim
CMD_VEL_PUBLISH_RATE = 5    # Hz — how often to re-publish cmd_vel during motion
DOCKER_TIMEOUT = 60         # seconds — max time for a docker exec call
ROBOT_NAMESPACE = "robot1"
# ------------------------------------------------------------------------------------


class SimClient:
    """Controls simulated Go2 in Gazebo via docker exec into the ROS 2 container."""

    def __init__(self):
        self._container: str = "simulator-gui"
        self._trot_activated: bool = False

    def connect(self, container: str = "simulator-gui") -> None:
        """Verify the Docker container is running."""
        self._container = container
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0 or "true" not in result.stdout.lower():
            raise ConnectionError(
                f"Container '{container}' is not running. "
                "Start it with: docker compose -f docker/compose.yml up simulator"
            )

    def move_distance(self, forward: float = 0.0, right: float = 0.0) -> dict:
        """Move robot by (forward, right) meters using timed open-loop control."""
        distance = math.hypot(forward, right)
        if distance < 0.01:
            return {"status": "ok", "msg": "distance too small, skipped"}
        if distance > 3.0:
            return {"status": "error", "msg": f"distance {distance:.2f}m exceeds 3.0m limit"}

        self._ensure_trot_mode()

        speed = SIM_SPEED
        duration = distance / speed

        # Compute velocity components (body frame)
        angle = math.atan2(right, forward)
        vx = speed * math.cos(angle)
        vy = -speed * math.sin(angle)  # ROS convention: positive y = left

        # Publish cmd_vel repeatedly for the duration
        t0 = time.time()
        interval = 1.0 / CMD_VEL_PUBLISH_RATE

        while (time.time() - t0) < duration:
            self._pub_cmd_vel(vx, vy, 0.0)
            time.sleep(interval)

        self._pub_cmd_vel(0.0, 0.0, 0.0)
        elapsed = time.time() - t0

        return {
            "status": "ok",
            "distance_moved": round(distance, 3),
            "elapsed_s": round(elapsed, 2),
            "mode": "sim",
        }

    def rotate(self, degrees: float) -> dict:
        """Rotate robot by degrees (positive=CCW, negative=CW)."""
        if abs(degrees) > 360:
            return {"status": "error", "msg": "rotation limited to ±360 degrees"}

        self._ensure_trot_mode()

        rad = math.radians(abs(degrees))
        duration = rad / SIM_YAW_RATE
        yaw_rate = SIM_YAW_RATE if degrees > 0 else -SIM_YAW_RATE

        t0 = time.time()
        interval = 1.0 / CMD_VEL_PUBLISH_RATE

        while (time.time() - t0) < duration:
            self._pub_cmd_vel(0.0, 0.0, yaw_rate)
            time.sleep(interval)

        self._pub_cmd_vel(0.0, 0.0, 0.0)
        elapsed = time.time() - t0

        return {
            "status": "ok",
            "rotated_deg": round(degrees, 1),
            "elapsed_s": round(elapsed, 2),
            "mode": "sim",
        }

    def stand(self) -> dict:
        """Activate walk/trot mode (robot stands up)."""
        self._ros_service_call(
            f"/{ROBOT_NAMESPACE}/robot_behavior_command",
            "quadropted_msgs/srv/RobotBehaviorCommand",
            "{command: 'walk'}"
        )
        self._trot_activated = True
        return {"status": "ok", "msg": "standing (trot mode)", "mode": "sim"}

    def sit(self) -> dict:
        """Sit the robot down."""
        self._pub_cmd_vel(0.0, 0.0, 0.0)
        self._ros_service_call(
            f"/{ROBOT_NAMESPACE}/robot_behavior_command",
            "quadropted_msgs/srv/RobotBehaviorCommand",
            "{command: 'sit'}"
        )
        self._trot_activated = False
        return {"status": "ok", "msg": "sitting", "mode": "sim"}

    def stop(self) -> dict:
        """Stop all movement immediately."""
        self._pub_cmd_vel(0.0, 0.0, 0.0)
        return {"status": "ok", "msg": "stopped", "mode": "sim"}

    def status(self) -> dict:
        """Get robot status from the simulation."""
        try:
            odom_raw = self._docker_exec(
                "ros2 topic echo /robot1/odom --once --no-arr"
            )
            return {
                "status": "ok",
                "connected": True,
                "container": self._container,
                "trot_active": self._trot_activated,
                "mode": "sim",
                "odom_snippet": odom_raw[:500] if odom_raw else "no data",
            }
        except Exception as e:
            return {
                "status": "error",
                "connected": False,
                "msg": str(e),
                "mode": "sim",
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_trot_mode(self) -> None:
        """Activate TROT mode if not already done this session."""
        if not self._trot_activated:
            self.stand()

    def _pub_cmd_vel(self, vx: float, vy: float, vyaw: float) -> None:
        """Publish a single Twist message to cmd_vel."""
        twist = (
            f"{{linear: {{x: {vx:.4f}, y: {vy:.4f}, z: 0.0}}, "
            f"angular: {{x: 0.0, y: 0.0, z: {vyaw:.4f}}}}}"
        )
        self._docker_exec(
            f"ros2 topic pub --once /{ROBOT_NAMESPACE}/cmd_vel "
            f"geometry_msgs/msg/Twist \"{twist}\""
        )

    def _ros_service_call(self, service: str, srv_type: str, request: str) -> str:
        """Call a ROS 2 service."""
        return self._docker_exec(
            f"ros2 service call {service} {srv_type} \"{request}\""
        )

    def _docker_exec(self, ros_cmd: str) -> str:
        """Execute a ROS 2 command inside the Docker container."""
        full_cmd = [
            "docker", "exec", self._container,
            "bash", "-c",
            f"source /root/ws/install/setup.bash && {ros_cmd}"
        ]
        result = subprocess.run(
            full_cmd,
            capture_output=True, text=True, timeout=DOCKER_TIMEOUT
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(
                f"docker exec failed (code {result.returncode}): {stderr or result.stdout.strip()}"
            )
        return result.stdout.strip()
