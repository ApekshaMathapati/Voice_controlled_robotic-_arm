#!/usr/bin/env python3

"""
Voice recognition client for controlling a robotic arm via websockets.
This script runs on a remote laptop and sends voice commands to the main robot server.
"""

import asyncio
import websockets
import json
import sys
import time
import argparse
import speech_recognition as sr
import logging
import socket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("VoiceClient")

# Parse command line arguments
parser = argparse.ArgumentParser(description="Voice control client for robotic arm")
parser.add_argument("--debug", action="store_true", help="Enable debug mode with text input")
parser.add_argument("--server", default="localhost", help="Websocket server host (default: localhost)")
parser.add_argument("--port", type=int, default=8765, help="Websocket server port (default: 8765)")
args = parser.parse_args()

debug_mode = args.debug
server_host = args.server
server_port = args.port

# Commands that the system recognizes
VALID_COMMANDS = [
    "home", "up", "down", "left", "right", "open", "close", "stop", "position"
]

def process_command(text):
    """Process the recognized text and convert it to a command"""
    if not text:
        return None
    
    logger.info(f"Processing text: '{text}'")
    
    # Handle movement commands that might have variations or be partially recognized
    if "move" in text:
        words = text.split()
        move_index = words.index("move")
        
        # Check if there's a word after "move"
        if move_index + 1 < len(words):
            direction = words[move_index + 1]
            logger.debug(f"Direction word after 'move': '{direction}'")
            
            # Check for direction keywords
            if direction in ["up", "top", "higher", "above"]:
                logger.info("Detected UP command")
                return {"action": "up"}
            elif direction in ["down", "bottom", "lower", "below"]:
                logger.info("Detected DOWN command")
                return {"action": "down"}
            elif direction in ["left"]:
                logger.info("Detected LEFT command")
                return {"action": "left"}
            elif direction in ["right"]:
                logger.info("Detected RIGHT command")
                return {"action": "right"}
    
    # The original checks for exact phrases
    if "move up" in text:
        return {"action": "up"}
    if "move down" in text:
        return {"action": "down"}
    if "move left" in text:
        return {"action": "left"}
    if "move right" in text:
        return {"action": "right"}
    
    # Simple command processing - look for valid commands in the text
    for command in VALID_COMMANDS:
        if command in text:
            logger.info(f"Detected direct command: {command}")
            return {"action": command}
    
    logger.warning(f"Command not recognized in: '{text}'")
    return None

def recognize_speech():
    """Recognize speech using native Python speech recognition"""
    recognizer = sr.Recognizer()
    
    try:
        logger.info("Initializing microphone...")
        with sr.Microphone() as source:
            logger.info("Microphone initialized successfully")
            logger.info("Adjusting for ambient noise... (be quiet)")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            logger.info("Listening... Speak now.")
            
            try:
                # Set reasonable timeout and phrase time limit
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
                logger.info("Audio captured, processing speech...")
                
                # Try multiple recognition services in case one fails
                try:
                    text = recognizer.recognize_google(audio).lower()
                    logger.info(f"Google recognized: '{text}'")
                    return text
                except sr.RequestError:
                    # If Google fails, try Sphinx as fallback (works offline)
                    try:
                        logger.info("Google API failed, trying Sphinx...")
                        text = recognizer.recognize_sphinx(audio).lower()
                        logger.info(f"Sphinx recognized: '{text}'")
                        return text
                    except:
                        # If both fail, raise the original error
                        logger.error("All speech recognition services failed")
                        raise
                except sr.UnknownValueError:
                    logger.warning("Could not understand audio")
                    return None
                    
            except sr.WaitTimeoutError:
                logger.warning("No speech detected within timeout")
            except Exception as e:
                logger.error(f"Error during speech recognition: {e}")
                logger.error(f"Error type: {type(e).__name__}")
    except Exception as e:
        logger.error(f"Error initializing microphone: {e}")
        logger.error("Make sure your microphone is properly connected and working")
        logger.error("You might need to check your OS sound settings")
        
    return None

async def send_command(websocket, command_dict):
    """Send a command to the websocket server"""
    try:
        await websocket.send(json.dumps(command_dict))
        response = await websocket.recv()
        response_data = json.loads(response)
        logger.info(f"Server response: {response_data}")
        return True
    except Exception as e:
        logger.error(f"Error sending command: {e}")
        return False

async def debug_input_loop(websocket):
    """Loop for text input in debug mode"""
    logger.info("Debug mode active. Type commands instead of speaking them.")
    logger.info(f"Valid commands: {', '.join(VALID_COMMANDS)}")
    logger.info("Type 'exit' to quit.")
    
    while True:
        text = input("Enter command: ").lower()
        if text == "exit":
            break
            
        command = process_command(text)
        if command:
            logger.info(f"Sending command: {command}")
            await send_command(websocket, command)

async def voice_input_loop(websocket):
    """Loop for voice recognition input"""
    logger.info(f"Voice recognition active. Say one of: {', '.join(VALID_COMMANDS)}")
    logger.info("Say 'exit' or press Ctrl+C to exit.")
    
    try:
        while True:
            # Get speech input
            text = recognize_speech()
                
            # Check for exit command
            if text and "exit" in text:
                logger.info("Exit command detected")
                break
                
            # Process the command if speech was recognized
            if text:
                command = process_command(text)
                if command:
                    logger.info(f"Sending command: {command}")
                    await send_command(websocket, command)
            
            # Short delay to prevent CPU hogging
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Exiting voice control...")

async def main():
    """Main function"""
    logger.info("Voice Control Client for Robotic Arm")
    logger.info(f"Connecting to websocket server at ws://{server_host}:{server_port}")
    
    # Check if speech_recognition is installed
    if not debug_mode:
        try:
            import speech_recognition as sr
        except ImportError:
            logger.error("Error: speech_recognition module not found.")
            logger.error("Please install it using: pip install SpeechRecognition")
            sys.exit(1)
        
        # Check if PyAudio is installed (needed for Microphone)
        try:
            import pyaudio
        except ImportError:
            logger.error("Error: pyaudio module not found.")
            logger.error("Please install it using: pip install pyaudio")
            logger.error("On Linux, you might need: sudo apt-get install python3-pyaudio")
            logger.error("On Windows, you might need Microsoft Visual C++ 14.0 or greater")
            sys.exit(1)
    
    # Test basic network connectivity first
    logger.info(f"Testing network connectivity to {server_host}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        result = s.connect_ex((server_host, server_port))
        if result == 0:
            logger.info(f"TCP port {server_port} on {server_host} is reachable.")
        else:
            logger.error(f"TCP port {server_port} on {server_host} is NOT reachable (error code: {result}).")
            logger.error("Possible causes:")
            logger.error("1. Server is not running")
            logger.error("2. Firewall is blocking the connection")
            logger.error("3. Incorrect IP address or port")
            logger.error("4. Network connectivity issues")
            logger.error("\nTroubleshooting steps:")
            logger.error(f"- Ping the server: ping {server_host}")
            logger.error(f"- Check if server is running on {server_host}")
            logger.error("- Verify firewall settings on both computers")
            logger.error("- Make sure both computers are on the same network")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Network connectivity test failed: {e}")
        sys.exit(1)
    finally:
        s.close()
    
    # Connect to the websocket server using the simpler approach that works
    try:
        logger.info("Attempting websocket connection...")
        uri = f"ws://{server_host}:{server_port}"
        
        # Using the same simplified connection parameters as the successful test
        async with websockets.connect(uri, ping_interval=None, ping_timeout=None) as websocket:
            logger.info("Connected to server successfully!")
            
            # Run the appropriate input loop
            if debug_mode:
                await debug_input_loop(websocket)
            else:
                await voice_input_loop(websocket)
    except ConnectionRefusedError:
        logger.error(f"Connection refused. Is the server running at {server_host}:{server_port}?")
    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(f"Invalid status code: {e}")
        logger.error("The server may not be a websocket server.")
    except websockets.exceptions.InvalidHandshake as e:
        logger.error(f"Invalid handshake: {e}")
        logger.error("This usually indicates a problem with the websocket protocol negotiation.")
    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"Connection closed: {e}")
    except TimeoutError:
        logger.error("Connection timed out during the opening handshake.")
        logger.error("Please check:")
        logger.error("1. If the server is running and accessible")
        logger.error("2. If there's a firewall blocking the connection")
        logger.error("3. Try running the server with: --ws-host 0.0.0.0 to accept all connections")
        logger.error("4. Check if both computers are on the same network")
    except Exception as e:
        logger.error(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 