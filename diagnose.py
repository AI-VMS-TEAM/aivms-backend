#!/usr/bin/env python3
"""
Diagnostic script to check system status
"""
import socket
import requests
import json
import os
import subprocess

def check_port(port, name):
    """Check if a port is listening"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    
    if result == 0:
        print(f"✅ {name} is listening on port {port}")
        return True
    else:
        print(f"❌ {name} is NOT listening on port {port}")
        return False

def check_mediamtx_api():
    """Check if MediaMTX API is responding"""
    try:
        response = requests.get('http://localhost:5555/v3/config/paths/list', timeout=2)
        if response.status_code == 200:
            paths = response.json()
            print(f"✅ MediaMTX API is responding")
            print(f"   Configured paths: {list(paths.keys())}")
            return True
        else:
            print(f"❌ MediaMTX API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to MediaMTX API")
        return False
    except Exception as e:
        print(f"❌ Error checking MediaMTX API: {e}")
        return False

def check_flask_api():
    """Check if Flask API is responding"""
    try:
        response = requests.get('http://localhost:3000/api/cameras', timeout=2)
        if response.status_code == 200:
            cameras = response.json()
            print(f"✅ Flask API is responding")
            print(f"   Cameras: {len(cameras)}")
            for cam in cameras:
                print(f"     - {cam['name']} ({cam['ip']})")
            return True
        else:
            print(f"❌ Flask API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to Flask API")
        return False
    except Exception as e:
        print(f"❌ Error checking Flask API: {e}")
        return False

def check_hls_streams():
    """Check if HLS streams are accessible"""
    print("\nChecking HLS streams...")

    cameras = ['wisenet_front', 'dahua_front_cam', 'bosch_front_cam', 'axis_front_cam']

    for cam in cameras:
        url = f'http://localhost:8888/{cam}/index.m3u8'
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                print(f"✅ {cam}: Stream is available")
            else:
                print(f"❌ {cam}: Got status {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"❌ {cam}: Connection refused")
        except Exception as e:
            print(f"❌ {cam}: Error - {e}")

def check_files():
    """Check if required files exist"""
    print("\nChecking required files...")
    
    files = [
        'mediamtx.exe',
        'mediamtx.yml',
        'cameras.json',
        'app.py',
        'public/dashboard.html',
        'models/camera_manager.py'
    ]
    
    for file in files:
        if os.path.exists(file):
            print(f"✅ {file} exists")
        else:
            print(f"❌ {file} NOT FOUND")

def main():
    print("\n" + "="*60)
    print("AIVMS SYSTEM DIAGNOSTIC")
    print("="*60 + "\n")
    
    # Check files
    check_files()
    
    # Check ports
    print("\nChecking ports...")
    mediamtx_running = check_port(5555, "MediaMTX")
    flask_running = check_port(3000, "Flask")
    
    # Check APIs
    print("\nChecking APIs...")
    if mediamtx_running:
        check_mediamtx_api()
    else:
        print("⏭️  Skipping MediaMTX API check (not running)")
    
    if flask_running:
        check_flask_api()
    else:
        print("⏭️  Skipping Flask API check (not running)")
    
    # Check HLS streams
    if mediamtx_running:
        check_hls_streams()
    else:
        print("\n⏭️  Skipping HLS stream check (MediaMTX not running)")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    if mediamtx_running and flask_running:
        print("✅ Both services are running!")
        print("\nNext steps:")
        print("1. Open http://localhost:3000/dashboard.html in your browser")
        print("2. Press F12 to open Developer Tools")
        print("3. Go to Console tab")
        print("4. Check for any error messages")
        print("\nMediaMTX is on port 5555")
        print("Flask is on port 3000")
    elif not mediamtx_running and not flask_running:
        print("❌ Neither service is running!")
        print("\nTo start:")
        print("1. Terminal 1: ./mediamtx.exe")
        print("2. Terminal 2: python app.py")
    elif not mediamtx_running:
        print("❌ MediaMTX is not running!")
        print("\nTo start: ./mediamtx.exe")
    else:
        print("❌ Flask is not running!")
        print("\nTo start: python app.py")

if __name__ == '__main__':
    main()

