#!/usr/bin/env python3

"""
Controller for a voice-controlled robotic arm.
"""

from controller import Robot, Motor, PositionSensor
import sys
import socket
import json
import threading
import time

# Initialize the robot controller
robot = Robot()
timestep = int(robot.getBasicTimeStep())

# Get motor and position sensor devices
motor1 = robot.getDevice("motor1")
motor2 = robot.getDevice("motor2")
motor3 = robot.getDevice("motor3")
gripper_left = robot.getDevice("gripper_left")
gripper_right = robot.getDevice("gripper_right")

position_sensor1 = robot.getDevice("position_sensor1")
position_sensor2 = robot.getDevice("position_sensor2")
position_sensor3 = robot.getDevice("position_sensor3")
gripper_left_sensor = robot.getDevice("gripper_left_sensor")
gripper_right_sensor = robot.getDevice("gripper_right_sensor")

# Enable position sensors
position_sensor1.enable(timestep)
position_sensor2.enable(timestep)
position_sensor3.enable(timestep)
gripper_left_sensor.enable(timestep)
gripper_right_sensor.enable(timestep)

# Set motors to position control mode
motor1.setPosition(0.0)
motor2.setPosition(0.0)
motor3.setPosition(0.0)
gripper_left.setPosition(0.0)
gripper_right.setPosition(0.0)

# Create a socket server to receive commands from voice recognition script
class CommandServer:
    def __init__(self, host='localhost', port=65432):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(1)
        self.commands = []
        self.command_lock = threading.Lock()
        self.running = True
        
    def start(self):
        self.thread = threading.Thread(target=self.listen_for_commands)
        self.thread.daemon = True
        self.thread.start()
        
    def listen_for_commands(self):
        print("Command server listening on", self.host, "port", self.port)
        while self.running:
            try:
                client, addr = self.socket.accept()
                with client:
                    print('Connected by', addr)
                    data = client.recv(1024)
                    if data:
                        try:
                            command = json.loads(data.decode('utf-8'))
                            with self.command_lock:
                                self.commands.append(command)
                            client.sendall(b'Command received')
                        except json.JSONDecodeError:
                            print("Error: Invalid JSON data received")
                            client.sendall(b'Error: Invalid JSON data')
            except Exception as e:
                if self.running:
                    print("Error in command server:", e)
                    time.sleep(1)  # Prevent rapid reconnection attempts
    #Queue
    def get_next_command(self):
        with self.command_lock:
            if self.commands:
                return self.commands.pop(0)
            return None
    
    def stop(self):
        self.running = False
        self.socket.close()

# Start the command server
cmd_server = CommandServer()
cmd_server.start()

# Function to control both gripper motors together
def set_gripper_position(position):
    """Set gripper position where 0.0 is closed and 1.0 is open"""
    # Ensure motors have velocity set
    gripper_left.setVelocity(0.5)
    gripper_right.setVelocity(0.5)
    
    # Convert 0-1 range to actual gripper positions
    # For the slider joints, positive values move them apart (open)
    if position <= 0:
        # Closed position
        gripper_left.setPosition(0.0)
        gripper_right.setPosition(0.0)
    else:
        # Map the input position (0-1) to the gripper range (0-0.02)
        # Clamp to maximum opening of 0.02
        gripper_pos = min(position * 0.02, 0.02)
        gripper_left.setPosition(gripper_pos)
        gripper_right.setPosition(gripper_pos)

# Dictionary of predefined positions and movements
positions = {
    "home": {"motor1": 0.0, "motor2": 0.0, "motor3": 0.0, "gripper": 0.0},
    # For directional commands, we'll use relative movements defined later
    "open": {"motor1": None, "motor2": None, "motor3": None, "gripper": 0.0},
    "close": {"motor1": None, "motor2": None, "motor3": None, "gripper": 1.0},
}

# Define movement increments for relative motion commands
MOVEMENT_INCREMENT = 0.3  # radians (for left/right)
MOVEMENT_INCREMENT_VERTICAL = 0.2  # radians 

# Motor limit settings
MOTOR_LIMITS = {
    "motor1": {"min": -3.14, "max": 3.14},  # Full rotation limits
    "motor2": {"min": -1.57, "max": 1.57},  # -90 to +90 degrees
    "motor3": {"min": -1.57, "max": 1.57},  # -90 to +90 degrees
}

# Function to move a motor by a relative amount and respect limits
def move_motor_relative(motor, sensor, increment, motor_name):
    current_pos = sensor.getValue()
    target_pos = current_pos + increment
    
    # Apply limits
    limits = MOTOR_LIMITS.get(motor_name, {"min": -float("inf"), "max": float("inf")})
    if target_pos < limits["min"]:
        target_pos = limits["min"]
        print(f"[LIMIT] {motor_name} reached minimum limit of {limits['min']}")
    elif target_pos > limits["max"]:
        target_pos = limits["max"]
        print(f"[LIMIT] {motor_name} reached maximum limit of {limits['max']}")
    
    print(f"[DEBUG] Moving {motor_name}: Current={current_pos:.2f}, Target={target_pos:.2f}, Increment={increment:.2f}")
    motor.setPosition(target_pos)
    return target_pos

# Function to more carefully handle vertical movements (up/down)
def move_vertical(motor2, motor3, sensor2, sensor3, increment):
    # For vertical movement, ensure the motors move in a coordinated way
    # First move motor2, then motor3 with a slightly smaller increment
    # Move elbow joint (motor2) first
    move_motor_relative(motor2, sensor2, increment, "motor2")
    
    # Calculate a slightly different increment for motor3 to maintain smooth motion
    # This helps prevent the arm from trying to stretch or compress unnaturally
    m3_increment = increment * 0.9  # Slightly smaller increment for wrist joint
    move_motor_relative(motor3, sensor3, m3_increment, "motor3")

# Main control loop
print("Robot controller started")
print("[CONFIG] Movement increments - Horizontal:", MOVEMENT_INCREMENT, "Vertical:", MOVEMENT_INCREMENT_VERTICAL, "radians")
print("[CONFIG] Motor limits:", MOTOR_LIMITS)

# Set motor velocities to improve smoothness
motor1.setVelocity(1.0)  # Slower rotation for base (horizontal)
motor2.setVelocity(0.8)  # Slower for vertical joints
motor3.setVelocity(0.8)  # Slower for vertical joints
gripper_left.setVelocity(0.5)  # Set velocity for gripper motor
gripper_right.setVelocity(0.5)  # Set velocity for gripper motor

while robot.step(timestep) != -1:
    # Check for new commands
    command = cmd_server.get_next_command()
    if command:
        print(f"[COMMAND] Received: {command}")
        
        # Handle command
        if 'action' in command:
            action = command['action'].lower()
            print(f"[ACTION] Processing: {action}")
            
            # Handle directional commands with relative movements
            if action == "right":
                # Move right - decrease motor1 angle by increment (negative is right)
                move_motor_relative(motor1, position_sensor1, -MOVEMENT_INCREMENT, "motor1")
                print(f"[MOVE] Right movement executed")
            
            elif action == "left":
                # Move left - increase motor1 angle by increment (positive is left)
                move_motor_relative(motor1, position_sensor1, MOVEMENT_INCREMENT, "motor1")
                print(f"[MOVE] Left movement executed")
            
            elif action == "up":
                # Move up
                move_vertical(motor2, motor3, position_sensor2, position_sensor3, MOVEMENT_INCREMENT_VERTICAL)
                print(f"[MOVE] Up movement executed")
            
            elif action == "down":
                # Move down
                move_vertical(motor2, motor3, position_sensor2, position_sensor3, -MOVEMENT_INCREMENT_VERTICAL)
                print(f"[MOVE] Down movement executed")
            
            elif action in positions:
                position = positions[action]
                print(f"[POSITION] Moving to '{action}' position: {position}")
                if position['motor1'] is not None:
                    motor1.setPosition(position['motor1'])
                if position['motor2'] is not None:
                    motor2.setPosition(position['motor2'])
                if position['motor3'] is not None:
                    motor3.setPosition(position['motor3'])
                if position['gripper'] is not None:
                    print(f"[GRIPPER] Setting gripper to position: {position['gripper']}")
                    set_gripper_position(position['gripper'])
                    gripper_left_pos = gripper_left_sensor.getValue()
                    gripper_right_pos = gripper_right_sensor.getValue()
                    print(f"[GRIPPER] Current positions: left={gripper_left_pos:.4f}, right={gripper_right_pos:.4f}")
                print(f"[POSITION] Completed move to position: {action}") 