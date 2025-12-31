"""
Production WSGI Server for AIVMS Backend
Uses gevent for async I/O and WebSocket support
"""
import sys
from gevent import monkey
monkey.patch_all()

from app import app, socketio

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 AIVMS Backend - Production Server")
    print("=" * 60)
    print("Server: gevent WSGI")
    print("Host: 0.0.0.0")
    print("Port: 3000")
    print("WebSocket: Enabled")
    print("=" * 60)
    
    # Run with gevent WSGI server
    socketio.run(
        app,
        host='0.0.0.0',
        port=3000,
        debug=False,
        use_reloader=False,
        log_output=True
    )

