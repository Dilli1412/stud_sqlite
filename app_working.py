import streamlit as st
import sqlite3
import hashlib
import os
import zipfile
import io
from werkzeug.utils import secure_filename
import re
import pandas as pd

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
                 (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, email TEXT, course TEXT,
                 FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    # Check if columns exist, if not, add them
    c.execute("PRAGMA table_info(students)")
    columns = [column[1] for column in c.fetchall()]
    new_columns = ['resume_path', 'photo_path', 'student_id', 'register_no', 'academic_year']
    for col in new_columns:
        if col not in columns:
            c.execute(f'ALTER TABLE students ADD COLUMN {col} TEXT')
    
    c.execute('''CREATE TABLE IF NOT EXISTS pending_registrations
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, name TEXT, email TEXT, course TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS courses
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE)''')
    conn.commit()
    conn.close()

# Call init_db() to ensure all necessary columns are added
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

def save_file(file, folder):
    if not os.path.exists(folder):
        os.makedirs(folder)
    file_path = os.path.join(folder, secure_filename(file.name))
    with open(file_path, 'wb') as f:
        f.write(file.getbuffer())
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
    if not email.endswith('@srmist.edu.in'):
        return False, "Please use an email address with the domain srmist.edu.in"
    
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO pending_registrations (username, password, name, email, course) VALUES (?, ?, ?, ?, ?)',
                  (username, hash_password(password), name, email, course))
        conn.commit()
        return True, "Registration submitted successfully! Please wait for admin approval."
    except sqlite3.IntegrityError:
        return False, "Username already exists. Please choose a different username."
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
    st.set_page_config(page_title = "Student Portal", layout="wide")
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
            success, message = register_student(username, password, name, email, course)
            if success:
                st.success(message)
            else:
                st.error(message)
        else:
            st.error('Please fill in all fields')

def student_view():
    # Ensure session state is properly managed
    if 'user' not in st.session_state or st.session_state.user is None:
        st.error("User not logged in.")
        return

    st.subheader(f'Student Dashboard - Welcome, {st.session_state.user["username"] if "username" in st.session_state.user else "User"}!')

    if st.sidebar.button('Logout'):
        st.session_state.user_logged_in = False
        st.session_state.user = None
        st.session_state.user_role = None
        st.rerun()

    user_id = st.session_state.user['id']  # Extract user ID from session state directly

    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM students WHERE user_id=?', (user_id,))
    student = c.fetchone()
    conn.close()

    if student:
        # Convert sqlite3.Row to dictionary if necessary
        student_dict = dict(student) if isinstance(student, sqlite3.Row) else student

        col1, col2 = st.columns([3, 1])

        with col1:
            st.write(f"Name: {student_dict['name']}")
            st.write(f"Email: {student_dict['email']}")
            st.write(f"Course: {student_dict['course']}")
            st.write(f"Student ID: {student_dict['student_id']}")
            st.write(f"Register No: {student_dict['register_no']}")
            st.write(f"Academic Year: {student_dict['academic_year']}")

        with col2:
            if student_dict.get('photo_path'):
                st.image(student_dict['photo_path'], caption='Profile Photo', use_column_width=True)
            else:
                st.write("No profile photo available.")
            
            if student_dict.get('resume_path'):
                with open(student_dict['resume_path'], "rb") as file:
                    st.download_button(
                        label="Download Your Resume",
                        data=file,
                        file_name="your_resume.pdf",
                        mime="application/pdf"
                    )
            else:
                st.write("No resume file available.")

    st.subheader('Update Your Details')
    
    fields = ['name', 'email', 'course', 'student_id', 'register_no', 'academic_year']
    inputs = {}

    for field in fields:
        if field == 'course':
            inputs[field] = st.selectbox('Course', get_all_courses(), 
                index=get_all_courses().index(student['course']) if student and 'course' in student.keys() and student['course'] in get_all_courses() else 0)
        else:
            inputs[field] = st.text_input(field.capitalize(), value=student[field] if student and field in student.keys() else '')

    resume = st.file_uploader('Upload Resume (PDF only)', type='pdf')
    photo = st.file_uploader('Upload Profile Photo', type=['jpg', 'jpeg', 'png'])
    
    if st.button('Update Details'):
        if all(inputs.values()):
            resume_path = save_file(resume, 'resumes') if resume else (student['resume_path'] if student and 'resume_path' in student.keys() else None)
            photo_path = save_file(photo, 'photos') if photo else (student['photo_path'] if student and 'photo_path' in student.keys() else None)
            
            conn = get_db_connection()
            c = conn.cursor()
            if student:
    
                c.execute('''UPDATE students SET name=?, email=?, course=?, student_id=?, register_no=?, academic_year=?, 
                            resume_path=?, photo_path=? WHERE user_id=?''', 
                            (inputs['name'], inputs['email'], inputs['course'], 
                            inputs['student_id'], inputs['register_no'], inputs['academic_year'],
                            resume_path, photo_path, st.session_state.user['id']))
            else:
                
                c.execute('''INSERT INTO students (user_id, name, email, course, student_id, register_no, academic_year, 
                            resume_path, photo_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                            (st.session_state.user['id'], inputs['name'], inputs['email'], inputs['course'], 
                            inputs['student_id'], inputs['register_no'], inputs['academic_year'], resume_path, photo_path))

            conn.commit()
            conn.close()
            st.success('Details updated successfully!')
            st.rerun()
        else:
            st.error('Please fill in all fields')

def delete_student(student_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM students WHERE id = ?', (student_id,))
    conn.commit()
    conn.close()

def admin_view():
    st.subheader('Admin View')
    
    if st.sidebar.button('Logout'):
        st.session_state.user = None
        st.rerun()
    
    tab1, tab2, tab3, tab4 = st.tabs(["Student List", "Student Details", "Pending Registrations", "Course Management"])
    
    with tab1:
        st.subheader('Student List')
        # Search and Filter Options
        col1, col2 = st.columns(2)
        with col1:
            search_query = st.text_input('Search by name or email', key='search_query_tab1')
        with col2:
            courses = ['All'] + get_all_courses()
            course_filter = st.selectbox('Filter by course', courses, key='course_filter_tab1')
        
        if course_filter == 'All':
            course_filter = None
        # Fetch and display students
        students = search_students(search_query, course_filter)
        
        if students:
            # Convert sqlite3.Row objects to dictionaries
            students = [dict(student) for student in students]
            
            # Create a DataFrame for display
            df = pd.DataFrame(students)
            
            # Define the desired columns
            desired_columns = ['name', 'email', 'course', 'student_id', 'register_no', 'academic_year']
            
            # Only select columns that exist in the DataFrame
            existing_columns = [col for col in desired_columns if col in df.columns]
            
            # If no columns exist, display a message
            if not existing_columns:
                st.write("No student details available.")
            else:
                # Select only the existing columns
                df_display = df[existing_columns]
                st.dataframe(df_display)
            
            # Bulk resume download
            if st.button('Download All Resumes'):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                    for student in students:
                        if student.get('resume_path'):
                            file_name = f"{student.get('name', 'Unknown')}_{student.get('course', 'no_course')}_resume.pdf"
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
        st.subheader('Student Details')
        
        # Fetch students without filters
        students = search_students()
        
        if students:
            students = [dict(student) for student in students]
            for student in students:
                with st.expander(f"{student.get('name', 'Unknown')} - {student.get('email', 'No email')}"):
                    st.write(f"Course: {student.get('course', 'N/A')}")
                    st.write(f"Student ID: {student.get('student_id', 'N/A')}")
                    st.write(f"Register No: {student.get('register_no', 'N/A')}")
                    st.write(f"Academic Year: {student.get('academic_year', 'N/A')}")
    
                    # Display the profile photo
                    if student.get('photo_path') and os.path.exists(student['photo_path']):
                        st.image(student['photo_path'], caption='Profile Photo', width=200)
                    else:
                        st.write("No profile photo available.")
                    
                    # Display the resume download button
                    if student.get('resume_path') and os.path.exists(student['resume_path']):
                        with open(student['resume_path'], "rb") as file:
                            st.download_button(
                                label=f"Download {student.get('name', 'Unknown')}'s Resume",
                                data=file,
                                file_name=f"{student.get('name', 'Unknown')}_resume.pdf",
                                mime="application/pdf"
                            )
                    else:
                        st.write("No resume file available.")
                    
                    # Add a delete button for each student
                    if st.button(f"Delete {student.get('name', 'Unknown')}", key=f"delete_{student['id']}"):
                        delete_student(student['id'])
                        st.success(f"Deleted student {student.get('name', 'Unknown')}")
                        st.rerun()
        else:
            st.write('No student details found.')
    
    with tab3:
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
    
    with tab4:
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
            if col2.button('Delete', key=f"delete_course_{course}"):
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