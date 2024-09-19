import streamlit as st
import sqlite3
import hashlib
import os
import zipfile
import io
from werkzeug.utils import secure_filename
import pandas as pd
import base64


# Database setup
def get_db_connection():
    conn = sqlite3.connect('students.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, is_admin INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS students
                 (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, email TEXT, course TEXT, resume_path TEXT,
                 FOREIGN KEY (user_id) REFERENCES users(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_registrations
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, name TEXT, email TEXT, course TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS courses
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE)''')
    conn.commit()
    conn.close()

init_db()

# Helper functions
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_user(username, password):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username=? AND password=?', (username, hash_password(password)))
    user = c.fetchone()
    conn.close()
    return user

def is_admin(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT is_admin FROM users WHERE id=?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result['is_admin'] if result else False

def save_resume(resume):
    if not os.path.exists('resumes'):
        os.makedirs('resumes')
    file_path = os.path.join('resumes', secure_filename(resume.name))
    with open(file_path, 'wb') as f:
        f.write(resume.getbuffer())
    return file_path

def get_all_courses():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT name FROM courses')
    courses = [row['name'] for row in c.fetchall()]
    conn.close()
    return courses

def search_students(search_query='', course_filter=None):
    conn = get_db_connection()
    c = conn.cursor()
    query = '''SELECT * FROM students WHERE 
               (name LIKE ? OR email LIKE ?)'''
    params = [f'%{search_query}%', f'%{search_query}%']
    
    if course_filter:
        query += ' AND course = ?'
        params.append(course_filter)
    
    c.execute(query, params)
    students = c.fetchall()
    conn.close()
    return students

def register_student(username, password, name, email, course):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO pending_registrations (username, password, name, email, course) VALUES (?, ?, ?, ?, ?)',
                  (username, hash_password(password), name, email, course))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_pending_registrations():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM pending_registrations')
    registrations = c.fetchall()
    conn.close()
    return registrations

def approve_registration(registration_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM pending_registrations WHERE id = ?', (registration_id,))
    registration = c.fetchone()
    
    if registration:
        c.execute('INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)',
                  (registration['username'], registration['password']))
        user_id = c.lastrowid
        c.execute('INSERT INTO students (user_id, name, email, course) VALUES (?, ?, ?, ?)',
                  (user_id, registration['name'], registration['email'], registration['course']))
        c.execute('DELETE FROM pending_registrations WHERE id = ?', (registration_id,))
        conn.commit()
    
    conn.close()

def add_course(course_name):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO courses (name) VALUES (?)', (course_name,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_course(course_name):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM courses WHERE name = ?', (course_name,))
    conn.commit()
    conn.close()

# Streamlit app
st.logo("assets/srmist.jpg")
def main():
    st.set_page_config(page_title = "Students Portal", layout="wide")
    st.title('Student Management Portal')

    # Initialize session state
    if 'user' not in st.session_state:
        st.session_state.user = None

    # Check if user is logged in
    if st.session_state.user is None:
        page = st.sidebar.selectbox('Choose an action', ['Login', 'Register'])
        if page == 'Login':
            login()
        else:
            register()
    elif is_admin(st.session_state.user['id']):
        admin_view()
    else:
        student_view()

def login():
    st.subheader('Login')
    
    st.write("""
    ### Instructions:
    - For students: Use the username and password you created during registration.
    - For admins: Use your admin credentials.
    - If you don't have an account, please register using the sidebar option.
    """)
    
    username = st.text_input('Username')
    password = st.text_input('Password', type='password')
    
    if st.button('Login'):
        user = check_user(username, password)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error('Invalid username or password')

def register():
    st.subheader('Student Registration')
    
    username = st.text_input('Username')
    password = st.text_input('Password', type='password')
    name = st.text_input('Full Name')
    email = st.text_input('Email')
    course = st.selectbox('Course', get_all_courses())
    
    if st.button('Register'):
        if username and password and name and email and course:
            if not email.endswith('@srmist.edu.in'):
                st.error('Please use an email address with the domain srmist.edu.in')
            else:
                if register_student(username, password, name, email, course):
                    st.success('Registration submitted successfully! Please wait for admin approval.')
                else:
                    st.error('Username already exists. Please choose a different username.')
        else:
            st.error('Please fill in all fields')

def student_view():
    st.subheader(f"Welcome, {st.session_state.user['username']}!")
    
    if st.sidebar.button('Logout'):
        st.session_state.user = None
        st.rerun()
    
    st.subheader('Your Details')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM students WHERE user_id=?', (st.session_state.user['id'],))
    student = c.fetchone()
    conn.close()
    
    if student:
        st.write(f"Name: {student['name']}")
        st.write(f"Email: {student['email']}")
        st.write(f"Course: {student['course']}")
        if student['resume_path']:
            st.write('Resume uploaded')
    else:
        st.write('No details found. Please add your information.')
    
    st.subheader('Update Your Details')
    name = st.text_input('Name', value=student['name'] if student else '')
    email = st.text_input('Email', value=student['email'] if student else '')
    course = st.selectbox('Course', get_all_courses(), index=get_all_courses().index(student['course']) if student and student['course'] in get_all_courses() else 0)
    resume = st.file_uploader('Upload Resume (PDF only)', type='pdf')
    
    if st.button('Update Details'):
        if name and email and course:
            resume_path = save_resume(resume) if resume else (student['resume_path'] if student else None)
            conn = get_db_connection()
            c = conn.cursor()
            if student:
                c.execute('''UPDATE students SET name=?, email=?, course=?, resume_path=?
                             WHERE user_id=?''', (name, email, course, resume_path, st.session_state.user['id']))
            else:
                c.execute('''INSERT INTO students (user_id, name, email, course, resume_path)
                             VALUES (?, ?, ?, ?, ?)''', (st.session_state.user['id'], name, email, course, resume_path))
            conn.commit()
            conn.close()
            st.success('Details updated successfully!')
            st.rerun()
        else:
            st.error('Please fill in all fields')

def admin_view():
    st.subheader('Admin View')
    
    if st.sidebar.button('Logout'):
        st.session_state.user = None
        st.rerun()
    
    tab1, tab2, tab3 = st.tabs(["Student Details", "Pending Registrations", "Course Management"])
    
    with tab1:
        st.subheader('Student Details')

        # Search and Filter Options
        col1, col2 = st.columns(2)
        with col1:
            search_query = st.text_input('Search by name or email')
        with col2:
            courses = ['All'] + get_all_courses()
            course_filter = st.selectbox('Filter by course', courses)
        
        if course_filter == 'All':
            course_filter = None

        # Fetch and display students
        students = search_students(search_query, course_filter)
        
        if students:
            # Create a table to display student details
            table_data = []
            for student in students:
                download_button = ""
                if student['resume_path']:
                    with open(student['resume_path'], "rb") as file:
                        file_contents = file.read()
                    b64_contents = base64.b64encode(file_contents).decode()
                    download_button = f'''
                    <a href="data:application/pdf;base64,{b64_contents}" 
                       download="{student['name']}_resume.pdf" 
                       style="display: inline-block; padding: 0.25rem 0.75rem; 
                              background-color: #007bff; color: white; 
                              text-decoration: none; border-radius: 0.25rem;
                              font-size: 14px; font-weight: bold;
                              transition: background-color 0.3s ease;">
                        📄 Download Resume
                    </a>
                    '''
                else:
                    download_button = '''
                    <span style="display: inline-block; padding: 0.25rem 0.75rem; 
                                 background-color: #6c757d; color: white; 
                                 border-radius: 0.25rem; font-size: 14px;">
                        No Resume
                    </span>
                    '''
                table_data.append([
                    student['name'],
                    student['email'],
                    student['course'],
                    "✓" if student['resume_path'] else "✗",
                    download_button
                ])
            
            st.table(pd.DataFrame(table_data, columns=["Name", "Email", "Course", "Resume", "Download"]))

            # Bulk resume download
            if st.button('Download All Resumes'):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                    for student in students:
                        if student['resume_path']:
                            file_name = f"{student['name']}_{student['course']}_resume.pdf"
                            zip_file.write(student['resume_path'], file_name)
                
                zip_buffer.seek(0)
                st.download_button(
                    label="Download Resumes Zip",
                    data=zip_buffer,
                    file_name="student_resumes.zip",
                    mime="application/zip"
                )
        else:
            st.write('No student details found matching the search criteria.')
    
    with tab2:
        st.subheader('Pending Registrations')
        pending_registrations = get_pending_registrations()
        
        if pending_registrations:
            for registration in pending_registrations:
                st.write(f"Username: {registration['username']}")
                st.write(f"Name: {registration['name']}")
                st.write(f"Email: {registration['email']}")
                st.write(f"Course: {registration['course']}")
                if st.button(f"Approve {registration['username']}", key=f"approve_{registration['id']}"):
                    approve_registration(registration['id'])
                    st.success(f"Approved registration for {registration['username']}")
                    st.rerun()
                st.write('---')
        else:
            st.write('No pending registrations.')
    
    with tab3:
        st.subheader('Course Management')
        
        # Add new course
        new_course = st.text_input('Add New Course')
        if st.button('Add Course'):
            if new_course:
                if add_course(new_course):
                    st.success(f"Course '{new_course}' added successfully.")
                    st.rerun()
                else:
                    st.error(f"Course '{new_course}' already exists.")
            else:
                st.error("Please enter a course name.")
                    
        # List and delete courses
        st.subheader('Existing Courses')
        courses = get_all_courses()
        for course in courses:
            col1, col2 = st.columns([3, 1])
            col1.write(course)
            if col2.button('Delete', key=f"delete_{course}"):
                delete_course(course)
                st.success(f"Course '{course}' deleted successfully.")
                st.rerun()

if __name__ == '__main__':
    main()

    hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

