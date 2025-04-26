#!/usr/bin/env python3

"""
Voice recognition script for controlling a robotic arm in Webots.
This script is designed to work with Windows/WSL and sends commands to the Webots controller.

For WSL, we use a Windows-native solution for audio capture and pipe it to our script.
"""

import socket
import json
import sys
import os
import time
import threading
import queue
import subprocess
import tempfile
import argparse
import speech_recognition as sr

# Parse command line arguments
parser = argparse.ArgumentParser(description="Voice control for robotic arm in Webots")
parser.add_argument("--debug", action="store_true", help="Enable debug mode with text input")
parser.add_argument("--host", default="localhost", help="Server host (default: localhost)")
parser.add_argument("--port", type=int, default=65432, help="Server port (default: 65432)")
args = parser.parse_args()

debug_mode = args.debug
server_host = args.host
server_port = args.port

# Commands that the system recognizes
VALID_COMMANDS = [
    "home", "up", "down", "left", "right", "open", "close", "stop", "position"
]

def is_wsl():
    """Check if we're running under WSL"""
    if os.path.exists("/proc/version"):
        with open("/proc/version", "r") as f:
            if "microsoft" in f.read().lower():
                return True
    return False

def send_command(command_dict):
    """Send a command to the Webots controller via socket"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((server_host, server_port))
            s.sendall(json.dumps(command_dict).encode('utf-8'))
            response = s.recv(1024)
            print(f"Server response: {response.decode('utf-8')}")
            return True
    except ConnectionRefusedError:
        print("Error: Connection refused. Is the Webots simulation running?")
        return False
    except Exception as e:
        print(f"Error sending command: {e}")
        return False

def record_audio_windows():
    """
    Record audio using Windows' built-in tools and save to a temporary file.
    This function is used for WSL compatibility.
    """
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    temp_file.close()
    
    # Convert to Windows path
    windows_path = subprocess.check_output(["wslpath", "-w", temp_file.name]).decode('utf-8').strip()
    
    # Use PowerShell to record audio
    # This allows accessing the Windows audio system from WSL
    try:
        # Execute PowerShell command to record audio for 5 seconds
        ps_cmd = f"""
        Add-Type -AssemblyName System.Speech;
        $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine;
        $grammar = New-Object System.Speech.Recognition.DictationGrammar;
        $recognizer.LoadGrammar($grammar);
        $recognizer.SetInputToDefaultAudioDevice();
        $audio = $recognizer.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Single);
        Start-Sleep -Seconds 5;
        $recognizer.AudioState = [System.Speech.Recognition.AudioState]::Stopped;
        """
        
        subprocess.run(["powershell.exe", "-Command", ps_cmd], check=True)
        
        # Return the file path
        return temp_file.name
    except Exception as e:
        print(f"Error recording audio: {e}")
        os.unlink(temp_file.name)
        return None

def recognize_speech_wsl():
    """Recognize speech for WSL environment using Windows tools"""
    print("Listening for 5 seconds... Speak now.")
    
    # Record audio using Windows tools
    audio_file = record_audio_windows()
    if not audio_file:
        return None
    
    try:
        # Use speech_recognition to process the recorded audio
        r = sr.Recognizer()
        with sr.AudioFile(audio_file) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data)
            return text.lower()
    except sr.UnknownValueError:
        print("Could not understand audio")
    except sr.RequestError as e:
        print(f"Could not request results; {e}")
    except Exception as e:
        print(f"Error in speech recognition: {e}")
    finally:
        # Clean up temporary file
        if os.path.exists(audio_file):
            os.unlink(audio_file)
    
    return None

def recognize_speech_native():
    """Recognize speech using native Python speech recognition"""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening... Speak now.")
        recognizer.adjust_for_ambient_noise(source)
        try:
            audio = recognizer.listen(source, timeout=5)
            print("Processing speech...")
            text = recognizer.recognize_google(audio).lower()
            print(f"Recognized: {text}")
            return text
        except sr.WaitTimeoutError:
            print("No speech detected within timeout")
        except sr.UnknownValueError:
            print("Could not understand audio")
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
        except Exception as e:
            print(f"Error in speech recognition: {e}")
    return None

def process_command(text):
    """Process the recognized text and convert it to a command"""
    if not text:
        return None
    
    print(f"DEBUG - Processing text: '{text}'")
    
    # Handle movement commands that might have variations or be partially recognized
    if "move" in text:
        words = text.split()
        move_index = words.index("move")
        
        # Check if there's a word after "move"
        if move_index + 1 < len(words):
            direction = words[move_index + 1]
            print(f"DEBUG - Direction word after 'move': '{direction}'")
            
            # Check for direction keywords
            if direction in ["up", "top", "higher", "above"]:
                print("DEBUG - Detected UP command")
                return {"action": "up"}
            elif direction in ["down", "bottom", "lower", "below"]:
                print("DEBUG - Detected DOWN command")
                return {"action": "down"}
            elif direction in ["left"]:
                print("DEBUG - Detected LEFT command")
                return {"action": "left"}
            elif direction in ["right"]:
                print("DEBUG - Detected RIGHT command")
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
            print(f"DEBUG - Detected direct command: {command}")
            return {"action": command}
    
    print(f"Command not recognized in: '{text}'")
    return None

def debug_input_loop():
    """Loop for text input in debug mode"""
    print("Debug mode active. Type commands instead of speaking them.")
    print(f"Valid commands: {', '.join(VALID_COMMANDS)}")
    print("Type 'exit' to quit.")
    
    while True:
        text = input("Enter command: ").lower()
        if text == "exit":
            break
            
        command = process_command(text)
        if command:
            print(f"Sending command: {command}")
            send_command(command)

def voice_input_loop():
    """Loop for voice recognition input"""
    print(f"Voice recognition active. Say one of: {', '.join(VALID_COMMANDS)}")
    print("Press Ctrl+C to exit.")
    
    # Determine if we need WSL-specific handling
    wsl_mode = is_wsl()
    if wsl_mode:
        print("WSL detected, using Windows audio capture")
    else:
        print("Using native audio capture")
    
    try:
        while True:
            # Get speech input
            if wsl_mode:
                text = recognize_speech_wsl()
            else:
                text = recognize_speech_native()
                
            # Process the command if speech was recognized
            if text:
                command = process_command(text)
                if command:
                    print(f"Sending command: {command}")
                    send_command(command)
            
            # Short delay to prevent CPU hogging
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Exiting voice control...")

def main():
    """Main function"""
    print("Voice Control for Robotic Arm")
    print(f"Connecting to Webots controller at {server_host}:{server_port}")
    
    # Check if speech_recognition is installed
    try:
        import speech_recognition as sr
    except ImportError:
        print("Error: speech_recognition module not found.")
        print("Please install it using: pip install SpeechRecognition")
        sys.exit(1)
    
    # Check if PyAudio is installed (needed for Microphone)
    if not debug_mode and not is_wsl():
        try:
            import pyaudio
        except ImportError:
            print("Error: pyaudio module not found.")
            print("Please install it using: pip install pyaudio")
            print("On Linux, you might need: sudo apt-get install python3-pyaudio")
            print("On Windows, you might need Microsoft Visual C++ 14.0 or greater")
            sys.exit(1)
    
    # Run the appropriate input loop
    if debug_mode:
        debug_input_loop()
    else:
        voice_input_loop()

if __name__ == "__main__":
    main() 