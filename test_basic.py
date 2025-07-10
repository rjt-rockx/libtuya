#!/usr/bin/env python3
"""
Basic test script to verify the development environment setup.
"""

def test_basic_imports():
    """Test basic imports work."""
    print("Testing basic imports...")
    
    try:
        from libtuya.auth import TuyaAuthenticator
        print("✓ Auth module imported successfully")
    except Exception as e:
        print(f"✗ Auth import failed: {e}")
        return False
    
    try:
        # Test authenticator creation
        auth = TuyaAuthenticator()
        print("✓ TuyaAuthenticator created successfully")
    except Exception as e:
        print(f"✗ TuyaAuthenticator creation failed: {e}")
        return False
    
    return True

def test_dependencies():
    """Test that required dependencies are available."""
    print("\nTesting dependencies...")
    
    dependencies = [
        "click",
        "rich",
        "qrcode",
        "tinytuya",
        "tuya_sharing",
        "pytest",
        "black",
        "flake8",
        "mypy"
    ]
    
    success = True
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"✓ {dep} available")
        except ImportError:
            print(f"✗ {dep} missing")
            success = False
    
    return success

def test_project_structure():
    """Test that project structure is correct."""
    print("\nTesting project structure...")
    
    import os
    required_dirs = [
        "libtuya",
        "libtuya/auth",
        "libtuya/intelligence",
        "libtuya/devices",
        "libtuya/dps",
        "libtuya/recovery",
        "tests",
        "intelligence"
    ]
    
    success = True
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print(f"✓ {dir_name} exists")
        else:
            print(f"✗ {dir_name} missing")
            success = False
    
    return success

if __name__ == "__main__":
    print("LibTuya Development Environment Test")
    print("=" * 40)
    
    tests = [
        test_basic_imports,
        test_dependencies,
        test_project_structure
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 40)
    if all(results):
        print("✓ All tests passed! Development environment is ready.")
        exit(0)
    else:
        print("✗ Some tests failed. Please check the output above.")
        exit(1)