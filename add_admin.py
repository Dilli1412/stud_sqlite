import sqlite3
import hashlib

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

conn = sqlite3.connect('students.db')
c = conn.cursor()

admin_username = 'admin'
admin_password = 'adminpass'  # Change this to a secure password

c.execute('INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)',
          (admin_username, hash_password(admin_password), 1))

conn.commit()
conn.close()

print(f"Admin user '{admin_username}' added successfully.")