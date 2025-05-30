from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_migrate import Migrate # Added Migrate import
import bcrypt # For password hashing
import os
from datetime import datetime
import json # Added for json.dumps
from markupsafe import Markup # Added Markup import here

app = Flask(__name__)

# Configurations
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'project_management.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_very_secret_key_that_should_be_changed') # Load from env or use a default

db = SQLAlchemy(app)
migrate = Migrate(app, db) # Initialize Flask-Migrate
login_manager = LoginManager(app)
login_manager.login_view = 'login' # Redirect to 'login' view if user not logged in
login_manager.login_message_category = 'info' # Flash message category

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Database Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bio = db.Column(db.String(300), nullable=True)  # Short bio for profile
    accomplishments = db.Column(db.Text, nullable=True)  # Multiline accomplishments

    projects_owned = db.relationship('Project', backref='owner_user', lazy=True, foreign_keys='Project.owner_id')
    assigned_tasks = db.relationship('Task', backref='assignee_user', lazy=True, foreign_keys='Task.assignee_id')
    comments = db.relationship('Comment', backref='author_user', lazy=True)
    projects = db.relationship('Project', secondary='project_member', back_populates='members')

    def set_password(self, password):
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def __repr__(self):
        return f'<User {self.username}>'

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    archived = db.Column(db.Boolean, default=False, nullable=False)  # New field for archiving

    tasks = db.relationship('Task', backref='project', lazy=True, cascade="all, delete-orphan")
    members = db.relationship('User', secondary='project_member', back_populates='projects')

    def get_status(self):
        """Calculate project status based on tasks and archived state"""
        if self.archived:
            return 'Archived'
        
        if not self.tasks:
            return 'Active'  # No tasks yet, consider it active
        
        total_tasks = len(self.tasks)
        done_tasks = len([task for task in self.tasks if task.status == 'Done'])
        
        if done_tasks == total_tasks:
            return 'Completed'
        else:
            return 'Active'
    
    def get_completion_percentage(self):
        """Get completion percentage of tasks"""
        if not self.tasks:
            return 0
        
        total_tasks = len(self.tasks)
        done_tasks = len([task for task in self.tasks if task.status == 'Done'])
        return int((done_tasks / total_tasks) * 100) if total_tasks > 0 else 0

    def __repr__(self):
        return f'<Project {self.name}>'

project_member = db.Table('project_member',
    db.Column('project_id', db.Integer, db.ForeignKey('project.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role', db.String(50), nullable=True)
)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='To-Do')
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    priority = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    comments = db.relationship('Comment', backref='task', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else None,
            'start_date': self.start_date.strftime('%Y-%m-%d') if self.start_date else None,
            'due_date': self.due_date.strftime('%Y-%m-%d') if self.due_date else None,
            'project_name': self.project.name if self.project else None,
            'assignee_name': self.assignee_user.username if self.assignee_user else None,
            'url': url_for('edit_task', task_id=self.id, _external=False)
        }

    def __repr__(self):
        return f'<Task {self.title}>'

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Comment {self.id} on Task {self.task_id}>'

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    related_url = db.Column(db.String(255), nullable=True)

    user = db.relationship('User', backref=db.backref('notifications', lazy=True))

    def __repr__(self):
        return f'<Notification {self.id} for User {self.user_id}>'

@app.context_processor
def inject_notifications():
    if current_user.is_authenticated:
        unread_notifications_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return dict(unread_notifications_count=unread_notifications_count)
    return dict(unread_notifications_count=0)

# Routes
@app.route('/')
@login_required # Ensure user is logged in to see the dashboard
def index():
    # Fetch projects owned by the current user
    projects = Project.query.filter_by(owner_id=current_user.id).all()
    
    # Fetch all tasks for those projects
    tasks_by_status = {
        'To-Do': [],
        'In Progress': [],
        'To Be Review': [],
        'Done': []
    }
    
    all_tasks_for_user = []
    for project in projects:
        all_tasks_for_user.extend(project.tasks)
        
    for task in all_tasks_for_user:
        if task.status in tasks_by_status:
            tasks_by_status[task.status].append(task)
        else:
            # Handle tasks with unexpected statuses, e.g., add to a default list or log
            # For now, we'll assume statuses match the keys
            pass 
            
    # For the sidebar - list of projects owned by the user
    user_projects = Project.query.filter_by(owner_id=current_user.id).order_by(Project.name).all()

    # For the sidebar - list of all users (for Team Members display)
    all_users = User.query.order_by(User.username).all()

    return render_template('index.html', tasks_by_status=tasks_by_status, user_projects=user_projects, all_users=all_users)

@app.route('/calendar')
@login_required
def calendar_view():
    user_projects = Project.query.filter_by(owner_id=current_user.id).all()
    project_ids = [p.id for p in user_projects]
    
    tasks_with_due_dates = Task.query.filter(
        Task.project_id.in_(project_ids),
        Task.due_date.isnot(None)
    ).order_by(Task.due_date).all()

    # Convert tasks to list of dicts for JSON serialization
    tasks_for_calendar = [task.to_dict() for task in tasks_with_due_dates]

    all_users = User.query.order_by(User.username).all()
    
    return render_template(
        'calendar_view.html', 
        tasks_json=Markup(json.dumps(tasks_for_calendar)), # Pass JSON string for tasks
        user_projects=user_projects, 
        all_users=all_users
    )

@app.route('/timeline')
@login_required
def timeline_view():
    user_owned_projects = Project.query.filter_by(owner_id=current_user.id).all()
    
    timeline_items = []

    # Add projects to timeline items
    for project in user_owned_projects:
        if project.start_date and project.end_date:
            timeline_items.append({
                "id": f"project_{project.id}",
                "group": "Projects", # Group all projects under one label
                "content": project.name,
                "start": project.start_date.isoformat(),
                "end": project.end_date.isoformat(),
                "type": "background", # Or "range" if you want them to be distinct bars
                "style": "background-color: #d3d3d3; opacity: 0.5;" # Optional styling for project spans
            })

    # Fetch tasks for the user's projects
    project_ids = [p.id for p in user_owned_projects]
    tasks_for_timeline = Task.query.filter(
        Task.project_id.in_(project_ids),
        Task.start_date.isnot(None), # Ensure tasks have a start date
        Task.due_date.isnot(None)    # Ensure tasks have a due date (end date)
    ).order_by(Task.project_id, Task.start_date.asc()).all()

    # Add tasks to timeline items
    for task in tasks_for_timeline:
        timeline_items.append({
            "id": f"task_{task.id}",
            "group": task.project.name, # Group tasks by project name
            "content": task.title,
            "start": task.start_date.isoformat(),
            "end": task.due_date.isoformat(), # Using due_date as the end date for tasks
            "className": f"status-{task.status.lower().replace(' ', '-').replace('_', '-')}" # For styling
        })

    # Get all users and user_projects for sidebar consistency (already present in original code for sidebar)
    all_users = User.query.order_by(User.username).all()
    # user_projects is already fetched as user_owned_projects

    return render_template(
        'timeline_view.html',
        timeline_items_json=Markup(json.dumps(timeline_items)), # Pass timeline_items directly
        user_projects=user_owned_projects, # For sidebar
        all_users=all_users # For sidebar
    )

@app.route('/overview')
@login_required
def overview_view():
    user_projects = Project.query.filter_by(owner_id=current_user.id).order_by(Project.name).all()

    task_stats = {
        'To-Do': 0,
        'In Progress': 0,
        'To Be Review': 0,
        'Done': 0,
        'Total': 0
    }
    all_user_tasks = []
    project_ids = [p.id for p in user_projects]

    if project_ids:
        all_user_tasks = Task.query.filter(Task.project_id.in_(project_ids)).all()
    
    for task in all_user_tasks:
        if task.status in task_stats:
            task_stats[task.status] += 1
        task_stats['Total'] += 1

    recently_completed_tasks = Task.query.filter(
        Task.project_id.in_(project_ids),
        Task.status == 'Done'
    ).order_by(Task.updated_at.desc()).limit(5).all()

    upcoming_deadlines = Task.query.filter(
        Task.project_id.in_(project_ids),
        Task.due_date.isnot(None),
        Task.due_date >= datetime.utcnow().date(), # Tasks due today or in the future
        Task.status != 'Done' # Exclude completed tasks
    ).order_by(Task.due_date.asc()).limit(5).all()
    
    # For sidebar consistency
    all_users = User.query.order_by(User.username).all()

    return render_template(
        'overview_view.html',
        user_projects=user_projects,
        task_stats=task_stats,
        recently_completed_tasks=recently_completed_tasks,
        upcoming_deadlines=upcoming_deadlines,
        all_users=all_users # For sidebar
    )

@app.route('/notifications')
@login_required
def notifications_view():
    # Fetch all notifications for the current user, newest first
    user_notifications = Notification.query.filter_by(user_id=current_user.id)\
                                         .order_by(Notification.timestamp.desc()).all()
    
    # Removed automatic marking of all notifications as read.
    # This will now be handled by individual "mark as read" actions.

    # For sidebar consistency (assuming these are needed on the notifications page too)
    user_projects_sidebar = Project.query.filter_by(owner_id=current_user.id).order_by(Project.name).all()
    all_users_sidebar = User.query.order_by(User.username).all()

    return render_template('notifications.html', 
                           notifications=user_notifications, 
                           user_projects=user_projects_sidebar, 
                           all_users=all_users_sidebar)

@app.route('/notification/mark_read/<int:notification_id>', methods=['POST'])
@login_required
def mark_notification_as_read(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != current_user.id:
        flash('You do not have permission to modify this notification.', 'danger')
        return redirect(url_for('notifications_view'))
    
    if not notification.is_read:
        notification.is_read = True
        try:
            db.session.commit()
            # Flash message can be optional here to avoid too many messages
            # flash('Notification marked as read.', 'success') 
        except Exception as e:
            db.session.rollback()
            flash(f'Error marking notification as read: {str(e)}', 'danger')
            # Log error e
    return redirect(url_for('notifications_view'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not username or not email or not password or not confirm_password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        existing_user_email = User.query.filter_by(email=email).first()
        if existing_user_email:
            flash('Email address already registered.', 'warning')
            return redirect(url_for('register'))
        
        existing_user_username = User.query.filter_by(username=username).first()
        if existing_user_username:
            flash('Username already taken.', 'warning')
            return redirect(url_for('register'))

        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        try:
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error during registration: {str(e)}', 'danger')
            return redirect(url_for('register'))
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index')) # Or a dashboard
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return redirect(url_for('login'))

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash('Logged in successfully!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/projects', methods=['GET', 'POST'])
@login_required
def manage_projects():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None

        if not name:
            flash('Project name is required!', 'danger')
        else:
            new_project = Project(name=name, description=description, owner_id=current_user.id, start_date=start_date, end_date=end_date)
            db.session.add(new_project)
            try:
                db.session.commit()
                flash('Project added successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error adding project: {str(e)}', 'danger')
            return redirect(url_for('manage_projects'))

    # Get all projects for the user
    all_user_projects = Project.query.filter_by(owner_id=current_user.id).order_by(Project.created_at.desc()).all()
    
    # Organize projects by status
    active_projects = []
    completed_projects = []
    archived_projects = []
    
    for project in all_user_projects:
        status = project.get_status()
        if status == 'Archived':
            archived_projects.append(project)
        elif status == 'Completed':
            completed_projects.append(project)
        else:  # Active
            active_projects.append(project)
    
    # Sort projects within each category
    active_projects.sort(key=lambda p: p.start_date or p.created_at, reverse=True)
    completed_projects.sort(key=lambda p: p.end_date or p.updated_at, reverse=True)
    archived_projects.sort(key=lambda p: p.updated_at, reverse=True)
    
    # For backward compatibility, keep the original variables
    projects = active_projects + completed_projects  # Non-archived projects
    
    # For sidebar consistency - provide user_projects and all_users
    user_projects = Project.query.filter_by(owner_id=current_user.id).order_by(Project.name).all()
    all_users = User.query.order_by(User.username).all()
    
    return render_template('projects.html', 
                         projects=projects, 
                         active_projects=active_projects,
                         completed_projects=completed_projects,
                         archived_projects=archived_projects, 
                         user_projects=user_projects, 
                         all_users=all_users)

@app.route('/projects/archive/<int:project_id>', methods=['POST'])
@login_required
def archive_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.owner_id != current_user.id:
        flash('You do not have permission to archive this project.', 'danger')
        return redirect(url_for('manage_projects'))
    # Only allow archiving if all tasks are done
    if any(task.status != 'Done' for task in project.tasks):
        flash('Cannot archive project: not all tasks are completed.', 'warning')
        return redirect(url_for('manage_projects'))
    project.archived = True
    db.session.commit()
    flash('Project archived successfully!', 'success')
    return redirect(url_for('manage_projects'))

@app.route('/projects/unarchive/<int:project_id>', methods=['POST'])
@login_required
def unarchive_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.owner_id != current_user.id:
        flash('You do not have permission to unarchive this project.', 'danger')
        return redirect(url_for('manage_projects'))
    project.archived = False
    db.session.commit()
    flash('Project unarchived successfully!', 'success')
    return redirect(url_for('manage_projects'))

@app.route('/projects/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.owner_id != current_user.id:
        flash('You do not have permission to edit this project.', 'danger')
        return redirect(url_for('manage_projects'))

    if request.method == 'POST':
        if 'update_details' in request.form:
            name = request.form.get('name')
            description = request.form.get('description')
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')

            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None

            if not name:
                flash('Project name is required!', 'danger')
            else:
                project.name = name
                project.description = description
                project.start_date = start_date
                project.end_date = end_date
                project.updated_at = datetime.utcnow()
                try:
                    db.session.commit()
                    flash('Project details updated successfully!', 'success')
                    # No redirect here, stay on page to see member changes if any
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error updating project details: {str(e)}', 'danger')
        # Add other form handling for member management here if needed on POST

    # Get current members of the project
    current_members_ids = [user.id for user in project.members]
    # Ensure owner is always listed as a member visually, though relationship is through owner_id
    # or handle this by adding owner to members table on project creation.
    # For now, project.members should ideally reflect the project_member table.

    # Get users who are not members of this project yet
    potential_new_members = User.query.filter(User.id != project.owner_id, User.id.notin_(current_members_ids)).all()
    
    return render_template('edit_project.html', project=project, current_members=project.members, potential_new_members=potential_new_members)

@app.route('/project/<int:project_id>/add_member', methods=['POST'])
@login_required
def add_project_member(project_id):
    project = Project.query.get_or_404(project_id)
    if project.owner_id != current_user.id:
        flash('You do not have permission to manage members for this project.', 'danger')
        return redirect(url_for('manage_projects'))

    user_to_add_id = request.form.get('user_id')
    if not user_to_add_id:
        flash('Please select a user to add.', 'danger')
        return redirect(url_for('edit_project', project_id=project_id))

    user_to_add = User.query.get(user_to_add_id)
    if not user_to_add:
        flash('Selected user not found.', 'danger')
        return redirect(url_for('edit_project', project_id=project_id))

    if user_to_add in project.members or project.owner_id == user_to_add.id:
        flash(f'{user_to_add.username} is already a member or the owner of this project.', 'warning')
    else:
        project.members.append(user_to_add)
        try:
            db.session.commit()
            flash(f'{user_to_add.username} added to the project successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding member: {str(e)}', 'danger')
            
    return redirect(url_for('edit_project', project_id=project_id))

@app.route('/projects/delete/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.owner_id != current_user.id:
        flash('You do not have permission to delete this project.', 'danger')
        return redirect(url_for('manage_projects'))
        
    try:
        db.session.delete(project)
        db.session.commit()
        flash('Project deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting project: {str(e)}', 'danger')
    return redirect(url_for('manage_projects'))

# Task CRUD operations
@app.route('/project/<int:project_id>/tasks', methods=['GET'])
@login_required
def view_tasks(project_id):
    project = Project.query.get_or_404(project_id)
    if project.owner_id != current_user.id: # Basic authorization check
        flash('You do not have permission to view tasks for this project.', 'danger')
        return redirect(url_for('manage_projects'))
    tasks = sorted(project.tasks, key=lambda t: t.created_at, reverse=True)
    
    # Organize tasks by status for better display
    tasks_by_status = {
        'To-Do': [],
        'In Progress': [],
        'To Be Review': [],
        'Done': []
    }
    
    for task in tasks:
        if task.status in tasks_by_status:
            tasks_by_status[task.status].append(task)
    
    # Get completion statistics
    total_tasks = len(tasks)
    completed_tasks = len(tasks_by_status['Done'])
    completion_percentage = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
    
    # For sidebar consistency
    user_projects = Project.query.filter_by(owner_id=current_user.id).order_by(Project.name).all()
    all_users = User.query.order_by(User.username).all()
    
    return render_template('tasks.html', 
                         tasks=tasks, 
                         project=project, 
                         tasks_by_status=tasks_by_status,
                         completion_percentage=completion_percentage,
                         user_projects=user_projects,
                         all_users=all_users)

@app.route('/project/<int:project_id>/task/add', methods=['GET', 'POST'])
@login_required
def add_task(project_id):
    project = Project.query.get_or_404(project_id)
    if project.owner_id != current_user.id:
        flash('You do not have permission to add tasks to this project.', 'danger')
        return redirect(url_for('manage_projects'))

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        status = request.form.get('status', 'To-Do')
        assignee_id_str = request.form.get('assignee_id')
        start_date_str = request.form.get('start_date')
        due_date_str = request.form.get('due_date')

        assignee_id = None
        if assignee_id_str and assignee_id_str != "":
            try:
                assignee_id = int(assignee_id_str)
                if not User.query.get(assignee_id):
                    flash(f'Assignee user with ID {assignee_id} not found.', 'danger')
                    users = User.query.all()
                    return render_template('add_task.html', project=project, users=users, title=title, description=description, status=status, start_date=start_date_str, due_date=due_date_str)
            except ValueError:
                flash('Invalid Assignee ID format.', 'danger')
                users = User.query.all()
                return render_template('add_task.html', project=project, users=users, title=title, description=description, status=status, start_date=start_date_str, due_date=due_date_str)

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None

        if not title:
            flash('Task title is required!', 'danger')
        else:
            new_task = Task(
                project_id=project_id,
                title=title,
                description=description,
                status=status,
                assignee_id=assignee_id,
                start_date=start_date,
                due_date=due_date
            )
            db.session.add(new_task)
            try:
                db.session.commit()
                flash('Task added successfully!', 'success')

                # Create notification if task is assigned
                if new_task.assignee_id:
                    notification_message = f"You have been assigned a new task: '{new_task.title}' in project '{new_task.project.name}'."
                    related_url = url_for('edit_task', task_id=new_task.id)
                    notification = Notification(
                        user_id=new_task.assignee_id,
                        message=notification_message,
                        related_url=related_url
                    )
                    db.session.add(notification)
                    db.session.commit() # Commit notification

                return redirect(url_for('view_tasks', project_id=project_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error adding task: {str(e)}', 'danger')
    
    users = User.query.all() # To populate assignee dropdown
    return render_template('add_task.html', project=project, users=users)

@app.route('/task/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.project
    if project.owner_id != current_user.id:
        flash('You do not have permission to edit this task.', 'danger')
        return redirect(url_for('view_tasks', project_id=project.id))

    if request.method == 'POST':
        original_assignee_id = task.assignee_id # Store original assignee

        task.title = request.form.get('title')
        task.description = request.form.get('description')
        task.status = request.form.get('status')
        assignee_id_str = request.form.get('assignee_id')
        start_date_str = request.form.get('start_date')
        due_date_str = request.form.get('due_date')

        if assignee_id_str and assignee_id_str != "None" and assignee_id_str != "":
            try:
                assignee_id = int(assignee_id_str)
                if User.query.get(assignee_id):
                    task.assignee_id = assignee_id
                else:
                    flash(f'Assignee user with ID {assignee_id} not found. Task not updated with this assignee.', 'warning')
                    # Keep existing assignee or set to None if that's desired behavior
            except ValueError:
                flash('Invalid Assignee ID format. Assignee not updated.', 'warning')
        else:
            task.assignee_id = None # Unassign if empty or "None"

        task.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        task.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        
        task.updated_at = datetime.utcnow()

        if not task.title:
            flash('Task title is required!', 'danger')
        else:
            try:
                db.session.commit()
                # Auto-archive if all tasks are now done
                if project and not project.archived:
                    if project.tasks and all(t.status == 'Done' for t in project.tasks):
                        project.archived = True
                        db.session.commit()
                flash('Task updated successfully!', 'success')

                # Check if assignee changed and needs notification
                new_assignee_id = task.assignee_id
                if new_assignee_id and new_assignee_id != original_assignee_id:
                    notification_message = f"Task '{task.title}' in project '{task.project.name}' has been assigned to you."
                    if original_assignee_id is None:
                        notification_message = f"You have been assigned a new task: '{task.title}' in project '{task.project.name}'."
                    else:
                        notification_message = f"Task '{task.title}' (previously assigned to {task.assignee_user.username if task.assignee_user else 'someone else'}) in project '{task.project.name}' has now been assigned to you."
                        # We might want to notify the previous assignee too, if any, that the task was reassigned.
                        # For now, only notifying the new assignee.

                    related_url = url_for('edit_task', task_id=task.id)
                    notification = Notification(
                        user_id=new_assignee_id,
                        message=notification_message,
                        related_url=related_url
                    )
                    db.session.add(notification)
                    db.session.commit() # Commit notification

                return redirect(url_for('view_tasks', project_id=project.id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating task: {str(e)}', 'danger')

    users = User.query.all()
    return render_template('edit_task.html', task=task, project=project, users=users)

@app.route('/task/delete/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.project
    if project.owner_id != current_user.id:
        flash('You do not have permission to delete this task.', 'danger')
        return redirect(url_for('view_tasks', project_id=project.id))
        
    project_id = task.project_id 
    try:
        db.session.delete(task)
        db.session.commit()
        flash('Task deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting task: {str(e)}', 'danger')
    return redirect(url_for('view_tasks', project_id=project_id))

@app.route('/task/update_status', methods=['POST'])
@login_required
def update_task_status():
    data = request.get_json()
    task_id = data.get('task_id')
    new_status = data.get('new_status')

    if not task_id or not new_status:
        return jsonify({'success': False, 'message': 'Missing task_id or new_status'}), 400

    task = Task.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Task not found'}), 404

    # Authorization check: Ensure the current user owns the project this task belongs to
    if task.project.owner_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    # Validate new_status if necessary (e.g., ensure it's one of the allowed statuses)
    allowed_statuses = ['To-Do', 'In Progress', 'To Be Review', 'Done']
    if new_status not in allowed_statuses:
        return jsonify({'success': False, 'message': f'Invalid status: {new_status}'}), 400

    task.status = new_status
    task.updated_at = datetime.utcnow()
    try:
        db.session.commit()
        # Auto-archive if all tasks are now done
        project = task.project
        if project and not project.archived:
            if project.tasks and all(t.status == 'Done' for t in project.tasks):
                project.archived = True
                db.session.commit()
        return jsonify({'success': True, 'message': 'Task status updated'})
    except Exception as e:
        db.session.rollback()
        # Log the exception e for server-side debugging
        print(f"Error updating task status: {str(e)}") 
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500

@app.route('/search')
@login_required
def search():
    query = request.args.get('query', '').strip()
    found_projects = []
    found_tasks = []

    if not query:
        flash('Please enter a search term.', 'info')
        # Or redirect back to index, or render search_results with a message
        return render_template('search_results.html', query=query, projects=found_projects, tasks=found_tasks)

    # Search in projects owned by the user
    # Using ilike for case-insensitive search
    found_projects = Project.query.filter(
        Project.owner_id == current_user.id,
        Project.name.ilike(f'%{query}%')
    ).all()

    # Search in tasks within projects owned by the user
    # This requires joining Project to filter by owner_id, then searching task title/description
    found_tasks = Task.query.join(Project).filter(
        Project.owner_id == current_user.id,
        db.or_(
            Task.title.ilike(f'%{query}%'),
            Task.description.ilike(f'%{query}%')
        )
    ).all()
    
    if not found_projects and not found_tasks:
        flash(f'No results found for "{query}".', 'warning')

    return render_template('search_results.html', query=query, projects=found_projects, tasks=found_tasks)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    if request.method == 'POST':
        new_username = request.form.get('username')
        new_email = request.form.get('email')
        new_bio = request.form.get('bio')
        new_accomplishments = request.form.get('accomplishments')
        if not new_username or not new_email:
            flash('Username and email are required.', 'danger')
        else:
            # Check for username/email conflicts
            existing_user = User.query.filter(User.username == new_username, User.id != current_user.id).first()
            existing_email = User.query.filter(User.email == new_email, User.id != current_user.id).first()
            if existing_user:
                flash('Username already taken.', 'warning')
            elif existing_email:
                flash('Email already registered.', 'warning')
            else:
                current_user.username = new_username
                current_user.email = new_email
                current_user.bio = new_bio
                current_user.accomplishments = new_accomplishments
                try:
                    db.session.commit()
                    flash('Profile updated successfully!', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error updating profile: {str(e)}', 'danger')
    return render_template('user_profile.html')

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def user_settings():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_new_password = request.form.get('confirm_new_password')
        if not current_password or not new_password or not confirm_new_password:
            flash('All password fields are required.', 'danger')
        elif not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
        elif new_password != confirm_new_password:
            flash('New passwords do not match.', 'danger')
        else:
            current_user.set_password(new_password)
            try:
                db.session.commit()
                flash('Password updated successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating password: {str(e)}', 'danger')
    return render_template('user_settings.html')

# Command to initialize database (Does NOT create a default user anymore)
@app.cli.command('init-db')
def init_db_command():
    """Creates the database tables."""
    with app.app_context():
        db.create_all()
        # Default user creation is removed; users should register.
    print('Initialized the database.')

if __name__ == '__main__':
    app.run(debug=True) 