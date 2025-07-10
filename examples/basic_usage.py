#!/usr/bin/env python3
"""
Basic usage example for libtuya authentication system.

This example demonstrates how to use the TuyaAuthenticator class to:
1. Authenticate with QR code
2. Discover devices with local keys
3. Send commands to devices
"""

import sys
import time
from libtuya.auth import TuyaAuthenticator


def main():
    """Main example function."""
    print("=== libtuya Authentication Example ===\n")
    
    # Initialize authenticator
    authenticator = TuyaAuthenticator()
    
    try:
        # Start QR code authentication
        print("Starting QR code authentication...")
        qr_display = authenticator.start_qr_auth()
        
        # Display QR code
        print(qr_display)
        
        # Wait for authentication
        print("Waiting for authentication...")
        session = authenticator.wait_for_auth(timeout=300)  # 5 minutes timeout
        
        print(f"✓ Authentication successful! Session UID: {session.uid}")
        print(f"✓ Session expires in {session.expires_in_minutes} minutes\n")
        
        # Discover devices
        print("Discovering devices...")
        devices = authenticator.get_devices_with_keys()
        
        if not devices:
            print("No devices found with local keys.")
            return
        
        print(f"Found {len(devices)} devices with local keys:\n")
        
        # Display device information
        for i, device in enumerate(devices, 1):
            print(f"{i}. {device.name} ({device.device_type})")
            print(f"   ID: {device.id}")
            print(f"   Category: {device.category}")
            print(f"   Local Key: {device.local_key}")
            print(f"   IP Address: {device.ip}")
            print(f"   Online: {'✓' if device.online else '✗'}")
            print(f"   Can Control Locally: {'✓' if device.can_control_locally else '✗'}")
            
            if device.status:
                print(f"   Status: {device.status}")
            
            print()
        
        # Example device control
        controllable_devices = authenticator.get_controllable_devices()
        
        if controllable_devices:
            print("Example device control:")
            device = controllable_devices[0]
            print(f"Controlling device: {device.name}")
            
            if device.category == "dj":  # Light
                print("Turning on light and setting brightness...")
                success = authenticator.send_command(device.id, [
                    {"code": "switch_1", "value": True},
                    {"code": "bright_value", "value": 800}
                ])
                
                if success:
                    print("✓ Light control command sent successfully")
                else:
                    print("✗ Failed to send light control command")
            
            elif device.category == "kg":  # Switch
                print("Turning on switch...")
                success = authenticator.send_command(device.id, [
                    {"code": "switch_1", "value": True}
                ])
                
                if success:
                    print("✓ Switch control command sent successfully")
                else:
                    print("✗ Failed to send switch control command")
            
            else:
                print(f"Device category '{device.category}' not handled in this example")
        
        # Session information
        print("\nSession Information:")
        session_info = authenticator.get_session_info()
        for key, value in session_info.items():
            print(f"  {key}: {value}")
        
    except KeyboardInterrupt:
        print("\n\nAuthentication cancelled by user.")
        sys.exit(1)
    
    except Exception as e:
        print(f"\n\nError: {e}")
        sys.exit(1)
    
    finally:
        # Clean up
        authenticator.close()
        print("\nAuthentication session closed.")


if __name__ == "__main__":
    main()