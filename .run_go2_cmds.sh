#!/bin/sh
cd /Users/ivanzhuravel/Downloads/go2_ros2_sim_py
echo "=== CMD 1: status ==="
python3 go2_real/go2_cli.py --sim status
EC1=$?
echo "EXIT_CODE: $EC1"
if [ $EC1 -ne 0 ]; then exit $EC1; fi

echo "=== CMD 2: walk --forward 0.6 ==="
python3 go2_real/go2_cli.py --sim walk --forward 0.6
EC2=$?
echo "EXIT_CODE: $EC2"
if [ $EC2 -ne 0 ]; then exit $EC2; fi

echo "=== CMD 3: walk --right -0.3 ==="
python3 go2_real/go2_cli.py --sim walk --right -0.3
EC3=$?
echo "EXIT_CODE: $EC3"
exit $EC3
