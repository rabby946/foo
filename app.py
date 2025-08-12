from flask import Flask, render_template, redirect, url_for, request, session, flash
from datetime import timedelta
from flask_sqlalchemy import SQLAlchemy
from flask import make_response
from xhtml2pdf import pisa
from io import BytesIO
from collections import Counter
from datetime import datetime
from sqlalchemy import func
from sklearn.base import BaseEstimator, TransformerMixin
import pandas as pd
import numpy as np

class AgeWeighter(BaseEstimator, TransformerMixin):
    def __init__(self, weight=1.5):
        self.weight = weight

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = X.copy()
        if isinstance(X, pd.DataFrame):
            X['age'] = X['age'] * self.weight
        elif isinstance(X, np.ndarray):
            X[:, 0] = X[:, 0] * self.weight
        return X

import joblib
import numpy as np


app = Flask(__name__)
app.secret_key = "key"
app.permanent_session_lifetime = timedelta(minutes=30)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:s118044@localhost:5432/highschool'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
pipeline = joblib.load('ml_model/player_value_pipeline.pkl')
# pipeline = joblib.load('ml_model/player_value_pipeline.pkl')

db = SQLAlchemy(app)

class PredictionHistory(db.Model):
    __tablename__ = "prediction_history"
    id = db.Column(db.Integer, primary_key=True)
    player_name = db.Column(db.String(100), nullable=False)
    predicted_value = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

class User(db.Model):
    __tablename__ = "users" 
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(200), nullable=False)
    predicted_player = db.Column(db.String(100))
    predicted_value = db.Column(db.Integer)
    predicted_count = db.Column(db.Integer)
    history = db.relationship("PredictionHistory", backref="user", lazy=True, cascade="all, delete")

    def __init__(self, name, password):
        self.name = name
        self.password = password  # Hash password

    @staticmethod
    def add_user(name, password):
        user = User.query.filter_by(name=name).first()
        if user:
            return False
        new_user = User(name=name, password=password)
        db.session.add(new_user)
        db.session.commit()
        return True

    @staticmethod
    def get_user(name):
        return User.query.filter_by(name=name).first()



    @staticmethod
    def update_prediction(name, new_player, new_value):
        user = User.query.filter_by(name=name).first()
        if user:
            user.predicted_player = new_player
            db.session.commit()
            user.predicted_value = new_value
            db.session.commit()
            if user.predicted_count is None:
                user.predicted_count = 1
            else:
                user.predicted_count += 1
            db.session.commit()
            history = PredictionHistory(player_name=new_player, predicted_value=new_value, user_id=user.id)
            db.session.add(history)
            db.session.commit()
            

@app.route("/home")
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/signup", methods=["POST", "GET"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        password = request.form.get("password")
        if not name or not password:
            flash("Please fill out all fields.")
            return redirect(url_for("signup"))
        if not User.add_user(name, password):
            flash(f"User '{name}' already exists")
            return redirect(url_for("signup"))
        flash("Congratulations! A new account has been created.")
        user = User.get_user(name)
        session["user"] = user.name
        return redirect(url_for("user", user=user.name))
    return render_template("signup.html")

@app.route("/login", methods=["POST", "GET"])
def login():
    if "user" in session:
        return redirect(url_for("user", user=session["user"]))
    if request.method == "POST":
        name = request.form.get("name")
        password = request.form.get("password")
        user = User.get_user(name)
        if user:
            if user.password != password:
                flash("Invalid password")
                return render_template("login.html")
            session["user"] = name
            return redirect(url_for("user", user=name))
        flash("User not found")
        return render_template("login.html")
    return render_template("login.html")

@app.route("/<user>")
def user(user):
    if "user" not in session:
        flash("Session timeout!")
        return redirect(url_for("login"))
    user_obj = User.get_user(user)
    if not user_obj:
        return redirect(url_for("login"))
    return render_template("user.html",user=user,player_name=user_obj.predicted_player if user_obj else None,
                           player_value=user_obj.predicted_value if user_obj else None,count=user_obj.predicted_count)
@app.route("/profile")
def profile():
    if "user" not in session:
        flash("Session timeout!")
        return redirect(url_for("login"))
    return redirect(url_for("user", user=session["user"]))
@app.route("/logout")
def logout():
    if "user" in session:
        session.pop("user", None)
        flash("Session logged out")
    else: 
        flash(f"already logged out !")
    return redirect(url_for("login"))

@app.route("/player/<player>/<vl>")
def player(player, vl):
    return render_template("player.html", player=player, vl=vl)
@app.route("/delete_account", methods=["POST", "GET"])
def delete_account():
    if "user" not in session:
        flash("You must be logged in to delete your account.")
        return redirect(url_for("login"))
    
    user = User.get_user(session["user"])
    if user:
        db.session.delete(user)
        db.session.commit()
        session.pop("user", None)
        flash("Your account and prediction history have been deleted.")
    return redirect(url_for("home"))

@app.route("/predict", methods=["POST", "GET"])
def predict():
    if "user" not in session:
        flash("Please log in first")
        return redirect(url_for("login"))
    if request.method == "POST":
        try:
            # Extract form inputs safely
            name = request.form.get("player_name")
            # age_str = request.form.get("age")
            pace_str = request.form.get("pace")
            shooting_str = request.form.get("shooting")
            passing_str = request.form.get("passing")
            dribbling_str = request.form.get("dribbling")
            defending_str = request.form.get("defending")
            physicality_str = request.form.get("physicality")
            # Check if any are missing
            if not all([pace_str, shooting_str, passing_str, dribbling_str, defending_str, physicality_str]):
                flash("Please fill in all fields.")
                return redirect(url_for("predict"))
            # Convert the rest to integers
            pace = int(pace_str)
            shooting = int(shooting_str)
            passing = int(passing_str)
            dribbling = int(dribbling_str)
            defending = int(defending_str)
            physicality = int(physicality_str)
            # Make prediction
            features = [[pace, shooting, passing, dribbling, defending, physicality]]
            pred_value = int(pipeline.predict(features)[0])*10
            # Save to user history
            user = User.get_user(session["user"])
            User.update_prediction(user.name, name, pred_value)
            flash("Prediction successful")
            return redirect(url_for("player", player=name, vl=pred_value))
        except ValueError:
            flash("Please enter valid numeric values.")
            return redirect(url_for("predict"))

    return render_template("predict.html")

@app.route("/history", methods=["POST", "GET"])
def history():
    if "user" not in session:
        flash("You must log in to view history.")
        return redirect(url_for("login"))
    
    user = User.get_user(session["user"])
    if not user:
        flash("User not found")
        return redirect(url_for("login"))
    history  = user.history
    history.reverse()
    if request.method == "POST":
        # Type = request.form.get("position")
        action = request.form.get("action")
        if action  != "Ascending":
            history.reverse()
        # return render_template("history.html", user=user, history=history)
    return render_template("history.html", user=user, history=history)

@app.route("/statistics")
def statistics():
    if "user" not in session:
        flash("You must log in to view statistics.")
        return redirect(url_for("login"))
    user_obj = User.get_user(session["user"])
    if not user_obj:
        return redirect(url_for("login"))
    # Pie chart data (prediction frequency by player)
    history = PredictionHistory.query.filter_by(user_id=user_obj.id).all()
    player_counter = Counter([p.player_name for p in history])
    pie_data = dict(player_counter)

    # Timeline chart data (grouped by date)
    timeline = db.session.query(
        func.date(PredictionHistory.timestamp),
        func.count()
    ).filter_by(user_id=user_obj.id).group_by(func.date(PredictionHistory.timestamp)).all()

    timeline_data = {
        'labels': [str(date) for date, _ in timeline],
        'counts': [count for _, count in timeline]
    }
    return render_template("statistics.html",user=user_obj.name,pie_data=pie_data,timeline_data=timeline_data)

@app.route("/download_pdf")
def download_pdf():
    if "user" not in session:
        flash("You must log in to download your prediction history.")
        return redirect(url_for("login"))

    user = User.get_user(session["user"])
    if not user:
        flash("User not found")
        return redirect(url_for("login"))

    rendered = render_template("history_pdf.html", user=user, history=user.history)
    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(rendered, dest=pdf)

    if pisa_status.err:
        flash("Error generating PDF")
        return redirect(url_for("history"))

    response = make_response(pdf.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={user.name}_prediction_history.pdf'
    return response

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)