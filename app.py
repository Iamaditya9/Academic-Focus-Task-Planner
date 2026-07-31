import datetime as dt
import csv
import io

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    send_file,
    flash,
)

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from config import Config
from models import db, User, Task
app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates"
)

app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


with app.app_context():
    db.create_all()

# ---------------------------
# Authentication
# ---------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()

        email = request.form.get("email", "").strip().lower()

        password = request.form.get("password", "")

        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "warning")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Email already exists.", "warning")
            return redirect(url_for("register"))

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )

        print("Registering:", username, email)
        db.session.add(user)
        db.session.commit()
        print("User saved successfully")

        flash("Registration successful!", "success")

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        print("Searching for:", email)
        print("Found user:", user)

        if user and check_password_hash(user.password_hash, password):

            user.last_login = dt.datetime.utcnow()

            db.session.commit()

            login_user(user)

            flash("Login successful!", "success")

            return redirect(url_for("index"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():

    logout_user()

    flash("Logged out successfully.", "success")

    return redirect(url_for("login"))
def parse_date(s):
    if not s:
        return None
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_stats(all_tasks):
    today = dt.date.today()
    week_end = today + dt.timedelta(days=7)

    total = len(all_tasks)
    completed = sum(1 for t in all_tasks if t["completed"])
    pending = total - completed

    due_today = 0
    due_this_week = 0

    for t in all_tasks:
        d = parse_date(t["due_date"])
        if not d:
            continue
        if d == today:
            due_today += 1
        if today <= d <= week_end:
            due_this_week += 1

    if total == 0:
        completion_pct = 0
    else:
        completion_pct = round((completed / total) * 100)

    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "due_today": due_today,
        "due_this_week": due_this_week,
        "completion_pct": completion_pct,
    }


def sort_and_filter(tasks, sort_by, priority_filter, status_filter):
    # Filter by priority
    if priority_filter != "all":
        tasks = [t for t in tasks if (t["priority"] or "").lower() == priority_filter.lower()]

    # Filter by completion status
    if status_filter == "pending":
        tasks = [t for t in tasks if not t["completed"]]
    elif status_filter == "completed":
        tasks = [t for t in tasks if t["completed"]]

    # Sorting
    if sort_by == "due":
        def sort_key(t):
            d = parse_date(t["due_date"])
            # None dates go to the end
            return (d is None, d or dt.date.max)
        tasks = sorted(tasks, key=sort_key)
    elif sort_by == "priority":
        order = {"High": 0, "Normal": 1, "Low": 2}
        tasks = sorted(tasks, key=lambda t: order.get(t["priority"], 3))
    elif sort_by == "course":
        tasks = sorted(tasks, key=lambda t: (t["course"] or "").lower())
    else:
        # default: most recent id last
        tasks = sorted(tasks, key=lambda t: t["id"])

    return tasks


# ---------------------------
# Dashboard / Home
# ---------------------------
@app.route("/")
@login_required
def index():

    sort_by = request.args.get("sort", "due")
    priority_filter = request.args.get("priority", "all")
    status_filter = request.args.get("status", "all")

    all_tasks = Task.query.filter_by(
        user_id=current_user.id
    ).all()

    tasks = []

    for task in all_tasks:
        tasks.append({
            "id": task.id,
            "title": task.title,
            "due_date": task.due_date,
            "priority": task.priority,
            "course": task.course,
            "completed": task.completed
        })

    stats = compute_stats(tasks)

    visible_tasks = sort_and_filter(
        tasks,
        sort_by,
        priority_filter,
        status_filter
    )

    return render_template(
        "index.html",
        tasks=visible_tasks,
        username=current_user.username,
        stats=stats,
        sort=sort_by,
        priority=priority_filter,
        status=status_filter
    )

# ---------------------------
# Task operations
# ---------------------------
@app.route("/tasks", methods=["GET", "POST"])
@login_required
def tasks_route():

    if request.method == "POST":

        task = Task(
            title=request.form.get("title"),
            due_date=request.form.get("due_date"),
            priority=request.form.get("priority"),
            course=request.form.get("course"),
            user_id=current_user.id
        )

        db.session.add(task)
        db.session.commit()

        flash("Task added successfully.", "success")

        return redirect(url_for("index"))

    tasks = Task.query.filter_by(
        user_id=current_user.id
    ).all()

    return jsonify([
        {
            "id": task.id,
            "title": task.title,
            "due_date": task.due_date,
            "priority": task.priority,
            "course": task.course,
            "completed": task.completed
        }
        for task in tasks
    ])


@app.route("/tasks/<int:task_id>", methods=["PATCH", "DELETE"])
@login_required
def modify_task(task_id):

    task = Task.query.filter_by(
        id=task_id,
        user_id=current_user.id
    ).first_or_404()

    if request.method == "PATCH":

       task.completed = not task.completed

       db.session.commit()

       return jsonify({"status": "ok"})

    db.session.delete(task)

    db.session.commit()

    return jsonify({"status": "deleted"})

@app.route("/export")
@login_required
def export_csv():

    tasks = Task.query.filter_by(
        user_id=current_user.id
    ).all()

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Title",
        "Due Date",
        "Priority",
        "Course",
        "Completed"
    ])

    for task in tasks:

        writer.writerow([
            task.id,
            task.title,
            task.due_date,
            task.priority,
            task.course,
            task.completed
        ])

    memory = io.BytesIO()

    memory.write(output.getvalue().encode())

    memory.seek(0)

    return send_file(
        memory,
        mimetype="text/csv",
        as_attachment=True,
        download_name="tasks.csv"
    )

if __name__ == '__main__':
    app.run(debug=True)
