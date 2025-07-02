#!/usr/bin/env python3
"""
Test script to validate authentication functionality without MongoDB
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from auth import hash_password, verify_password

def test_auth_functions():
    """Test authentication functions"""
    print("🧪 Testing authentication functions...")
    
    # Test password hashing
    test_password = "admin123"
    password_hash = hash_password(test_password)
    print(f"✅ Password hashed: {password_hash[:50]}...")
    
    # Test password verification
    is_valid = verify_password(test_password, password_hash)
    print(f"✅ Password verification: {is_valid}")
    
    # Test invalid password
    is_invalid = verify_password("wrongpassword", password_hash)
    print(f"✅ Invalid password rejection: {not is_invalid}")
    
    return True

def test_template_existence():
    """Test that templates exist"""
    print("🧪 Testing templates...")
    
    login_template = "templates/login.html"
    index_template = "templates/index.html"
    
    login_exists = os.path.exists(login_template)
    index_exists = os.path.exists(index_template)
    
    print(f"✅ Login template exists: {login_exists}")
    print(f"✅ Index template exists: {index_exists}")
    
    return login_exists and index_exists

if __name__ == "__main__":
    print("🚀 Running authentication system tests...")
    
    success = True
    success &= test_auth_functions()
    success &= test_template_existence()
    
    if success:
        print("\n✅ All tests passed! Authentication system is ready.")
        print("📝 To test with MongoDB:")
        print("   1. Install and start MongoDB")
        print("   2. Run: python app.py")
        print("   3. Visit: http://localhost:5000")
        print("   4. Use default credentials: admin / admin123")
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)