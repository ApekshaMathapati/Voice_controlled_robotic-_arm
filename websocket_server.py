#!/usr/bin/env python3

"""
Websocket server for robotic arm voice control.
This server runs on the same machine as the Webots simulation.

It receives voice commands from remote clients and forwards them to the Webots controller.
"""

import asyncio
import websockets
import json
import socket
import argparse
import logging
import sys
import platform
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WebsocketServer")

# Parse command line arguments
parser = argparse.ArgumentParser(description="Websocket server for robotic arm control")
parser.add_argument("--ws-host", default="0.0.0.0", help="Websocket host (default: 0.0.0.0)")
parser.add_argument("--ws-port", type=int, default=8765, help="Websocket port (default: 8765)")
parser.add_argument("--robot-host", default="localhost", help="Robot controller host (default: localhost)")
parser.add_argument("--robot-port", type=int, default=65432, help="Robot controller port (default: 65432)")
parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
args = parser.parse_args()

# Set log level based on verbosity
if args.verbose:
    logging.getLogger().setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)

# Global variables
CLIENTS = set()

def get_ip_addresses():
    """Get all IP addresses of this machine to help with debugging"""
    ip_addresses = []
    try:
        # Get hostname
        hostname = socket.gethostname()
        ip_addresses.append(f"Hostname: {hostname}")
        
        # Get all IP addresses
        try:
            host_ip = socket.gethostbyname(hostname)
            ip_addresses.append(f"Primary IP: {host_ip}")
        except:
            pass
            
        # Get all network interfaces
        if platform.system() == "Windows":
            # On Windows
            ip_config = os.popen('ipconfig').read()
            ip_addresses.append("Network interfaces:")
            for line in ip_config.split('\n'):
                if "IPv4 Address" in line:
                    ip_addresses.append(f"  {line.strip()}")
        else:
            # On Linux/Mac
            if_config = os.popen('ifconfig || ip addr').read()
            ip_addresses.append("Network interfaces:")
            for line in if_config.split('\n'):
                if "inet " in line and "127.0.0.1" not in line:
                    ip_addresses.append(f"  {line.strip()}")
    except Exception as e:
        ip_addresses.append(f"Error getting IP addresses: {e}")
    
    return ip_addresses

async def send_to_robot(command_dict):
    """Send a command to the Webots controller via socket"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((args.robot_host, args.robot_port))
            s.sendall(json.dumps(command_dict).encode('utf-8'))
            response = s.recv(1024)
            response_text = response.decode('utf-8')
            logger.info(f"Robot response: {response_text}")
            return response_text
    except ConnectionRefusedError:
        logger.error("Error: Connection refused. Is the Webots simulation running?")
        return "ERROR: Connection refused"
    except Exception as e:
        logger.error(f"Error sending command to robot: {e}")
        return f"ERROR: {str(e)}"

async def handle_client(websocket):
    """Handle a client connection"""
    client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    
    logger.info(f"New client connected: {client_info}")
    CLIENTS.add(websocket)
    
    try:
        # Send welcome message
        await websocket.send(json.dumps({"status": "ok", "message": "Connected to robot server"}))
        
        async for message in websocket:
            try:
                command = json.loads(message)
                logger.info(f"Received from {client_info}: {command}")
                
                # Forward the command to the robot
                if "action" in command:
                    response = await send_to_robot(command)
                    await websocket.send(json.dumps({"status": "ok", "response": response}))
                else:
                    await websocket.send(json.dumps({"status": "error", "message": "Invalid command format"}))
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from {client_info}")
                await websocket.send(json.dumps({"status": "error", "message": "Invalid JSON"}))
    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"Client disconnected: {client_info} - {e}")
    finally:
        if websocket in CLIENTS:
            CLIENTS.remove(websocket)

async def main():
    """Main function"""
    # Print diagnostic information
    logger.info("=== Websocket Server for Robotic Arm Control ===")
    
    # Print IP address information to help with connection
    ip_addresses = get_ip_addresses()
    logger.info("Server IP Address Information:")
    for ip_info in ip_addresses:
        logger.info(f"  {ip_info}")
    
    # Check if port is already in use
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex((args.ws_host if args.ws_host != "0.0.0.0" else "127.0.0.1", args.ws_port))
    if result == 0:
        logger.warning(f"Port {args.ws_port} is already in use! This might cause issues.")
    sock.close()

    # Start the server
    logger.info(f"Starting websocket server on {args.ws_host}:{args.ws_port}")
    logger.info(f"Will forward commands to robot at {args.robot_host}:{args.robot_port}")
    logger.info("Use Ctrl+C to stop the server")
    
    # Check if robot controller is reachable
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect((args.robot_host, args.robot_port))
            logger.info(f"Robot controller is reachable at {args.robot_host}:{args.robot_port}")
    except Exception as e:
        logger.warning(f"Robot controller is not reachable: {e}")
        logger.warning("Voice commands will be received but may not be forwarded to the robot")
        logger.warning("Make sure the Webots simulation is running")

    # Start the websocket server
    try:
        async with websockets.serve(
            handle_client, 
            args.ws_host, 
            args.ws_port,
            ping_interval=30,
            ping_timeout=10
        ):
            logger.info("Server started successfully!")
            await asyncio.Future()  # Run forever
    except OSError as e:
        logger.error(f"Failed to start server: {e}")
        if "Address already in use" in str(e):
            logger.error(f"Port {args.ws_port} is already in use. Try a different port.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1) 