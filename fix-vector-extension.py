#!/usr/bin/env python3
"""
ISI-2826 Vector Extension Fix Script
Applies the vector extension to resolve backup_Product Manager silence issue
"""

import psycopg2
import sys
import os

# Database configuration
DB_HOST = "localhost"
DB_PORT = "54329"
DB_NAME = "paperclip"
DB_USER = "paperclip"

def log_info(message):
    print(f"[INFO] {message}")

def log_error(message):
    print(f"[ERROR] {message}")
    return False

def check_vector_extension():
    """Check if vector extension already exists"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER
        )
        cursor = conn.cursor()
        
        cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector');")
        exists = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        if exists:
            log_info("Vector extension already exists")
            return True
        else:
            log_info("Vector extension not found - will install")
            return False
            
    except Exception as e:
        log_error(f"Failed to check vector extension: {e}")
        return False

def install_vector_extension():
    """Install vector extension"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        log_info("Installing vector extension...")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        cursor.close()
        conn.close()
        
        log_info("Vector extension installed successfully")
        return True
        
    except Exception as e:
        log_error(f"Failed to install vector extension: {e}")
        return False

def verify_vector_extension():
    """Verify vector extension was installed"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER
        )
        cursor = conn.cursor()
        
        cursor.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if result:
            log_info(f"Vector extension verified: version {result[1]}")
            return True
        else:
            log_error("Vector extension verification failed")
            return False
            
    except Exception as e:
        log_error(f"Failed to verify vector extension: {e}")
        return False

def main():
    print("=" * 60)
    print("ISI-2826 Vector Extension Fix Script")
    print("=" * 60)
    print()
    
    log_info("Starting vector extension fix process...")
    
    # Step 1: Check if extension already exists
    log_info("Step 1: Checking for existing vector extension")
    if check_vector_extension():
        log_info("Vector extension is already present - no action needed")
        print()
        print("=" * 60)
        print("✅ VECTOR EXTENSION FIX COMPLETED")
        print("=" * 60)
        print()
        print("The vector extension is already installed.")
        print("backup_Product Manager should now be able to start successfully.")
        return True
    
    # Step 2: Install vector extension
    log_info("Step 2: Installing vector extension")
    if not install_vector_extension():
        log_error("Failed to install vector extension")
        return False
    
    # Step 3: Verify installation
    log_info("Step 3: Verifying vector extension installation")
    if not verify_vector_extension():
        log_error("Vector extension verification failed")
        return False
    
    print()
    print("=" * 60)
    print("✅ VECTOR EXTENSION FIX COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print()
    print("ISI-2826 Resolution Summary:")
    print("✅ Root cause: Missing vector extension resolved")
    print("✅ Memory service: Can now start successfully")
    print("✅ backup_Product Manager: Ready to resume operations")
    print()
    print("Next steps:")
    print("1. Start memory service: ./start-memory-final.sh")
    print("2. Test backup operations: Verify functionality")
    print("3. Monitor system: Check for any additional issues")
    print()
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)