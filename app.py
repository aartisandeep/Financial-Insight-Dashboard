from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, validators
from sqlalchemy import extract
import calendar

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///transactions.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = '97cc1dbf11a242d12bb1dfa9a847b703'
db = SQLAlchemy(app)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    transactions = db.relationship('Transaction', backref='user', lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class RegistrationForm(FlaskForm):
    username = StringField('Username', [validators.InputRequired()])
    email = StringField('Email', [validators.Email(), validators.InputRequired()])
    password = PasswordField('Password', [validators.InputRequired(), validators.EqualTo('confirm', message='Passwords must match')])
    confirm = PasswordField('Repeat Password')
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    username = StringField('Username', [validators.InputRequired()])
    password = PasswordField('Password', [validators.InputRequired()])
    submit = SubmitField('Login')

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    transactions = db.relationship('Transaction', backref='category', lazy=True)


@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    data = request.json
    new_transaction = Transaction(amount=data['amount'], description=data['description'], user_id=session['user_id'])
    # new_transaction = Transaction(amount=data['amount'], description=data['description'])
    db.session.add(new_transaction)
    db.session.commit()
    return jsonify({"message": "Transaction added successfully!"}), 201

@app.route('/get_transactions', methods=['GET'])
def get_transactions():
    transactions = Transaction.query.filter_by(user_id=session['user_id']).order_by(Transaction.date.desc()).limit(10).all()
    transactions_data = [
        {"id": t.id, "date": t.date.strftime('%Y-%m-%d %H:%M:%S'), "amount": t.amount, "description": t.description}
        for t in transactions
    ]
    return jsonify(transactions_data)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        data = request.form
        transaction_date = datetime.strptime(data['transaction_date'], "%Y-%m-%d").date()
        new_transaction = Transaction(
            date=transaction_date,
            amount=data['amount'],
            description=data['description'],
            category_id=data['category'],
            user_id=session['user_id']
        )
        db.session.add(new_transaction)
        db.session.commit()
        return redirect(url_for('dashboard'))

    transactions = Transaction.query.filter_by(user_id=session['user_id']).order_by(Transaction.date.desc()).limit(10).all()
    categories = Category.query.all()

    # Filter the top_expenses by user_id
    top_expenses = db.session.query(
        Category.name, func.sum(Transaction.amount).label('total')
    ).join(Transaction).filter(Transaction.user_id == session['user_id']).group_by(Category.name).order_by(
        func.sum(Transaction.amount).desc()
    ).limit(3).all()

    # Retrieve monthly totals
    monthly_totals_raw = db.session.query(
        extract('year', Transaction.date).label('year'),
        extract('month', Transaction.date).label('month'),
        func.sum(Transaction.amount).label('total')
    ).filter_by(user_id=session['user_id']).group_by('year', 'month').all()

    # Convert raw monthly totals to a more suitable format
    monthly_totals = [{"month": calendar.month_abbr[item.month], "year": item.year, "total_amount": item.total} for item in monthly_totals_raw]

    return render_template('dashboard.html', transactions=transactions, categories=categories, top_expenses=top_expenses, monthly_totals=monthly_totals)

@app.route('/api/total_spending_last_24h', methods=['GET'])
def total_spending_last_24h():
    one_day_ago = datetime.utcnow() - timedelta(days=1)
    total = db.session.query(func.sum(Transaction.amount)).filter(Transaction.date > one_day_ago, Transaction.user_id == session['user_id']).scalar()
    return jsonify({"total_spending": total or 0})

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data) # Updated this line
        db.session.add(user)
        db.session.commit()
        flash('You are now registered!')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
            flash('Logged in successfully.')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.')
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.before_request
def require_login():
    allowed_routes = ['login', 'register']
    if request.endpoint not in allowed_routes and 'user_id' not in session:
        return redirect(url_for('login'))

def get_monthly_totals(user_id):
    monthly_totals = db.session.query(
        extract('year', Transaction.date).label('year'),
        extract('month', Transaction.date).label('month'),
        func.sum(Transaction.amount).label('total')
    ).filter_by(user_id=user_id).group_by('year', 'month').all()
    return monthly_totals

def calculate_trends(monthly_totals):
    trends = []
    for i in range(1, len(monthly_totals)):
        previous_month = monthly_totals[i-1]
        current_month = monthly_totals[i]

        difference = current_month.total - previous_month.total
        if difference > 0:
            trend = 'Upward'
        elif difference < 0:
            trend = 'Downward'
        else:
            trend = 'Stable'

        trends.append({
            'year': current_month.year,
            'month': current_month.month,
            'trend': trend,
            'difference': difference
        })
    return trends


if __name__ == "__main__":
    app.run(debug=True)




###########
#code below works perfectly till large graph

# from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
# from flask_sqlalchemy import SQLAlchemy
# from datetime import datetime, timedelta
# from sqlalchemy import func
# from werkzeug.security import generate_password_hash, check_password_hash
# from flask_wtf import FlaskForm
# from wtforms import StringField, PasswordField, SubmitField, validators
# from sqlalchemy import extract
# import calendar

# app = Flask(__name__)
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///transactions.db'
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['SECRET_KEY'] = '97cc1dbf11a242d12bb1dfa9a847b703'
# db = SQLAlchemy(app)

# class Transaction(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     date = db.Column(db.DateTime, default=datetime.utcnow)
#     amount = db.Column(db.Float, nullable=False)
#     description = db.Column(db.String(200), nullable=False)
#     user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
#     category_id = db.Column(db.Integer, db.ForeignKey('category.id'))


# class User(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(80), unique=True, nullable=False)
#     email = db.Column(db.String(120), unique=True, nullable=False)
#     password = db.Column(db.String(120), nullable=False)
#     transactions = db.relationship('Transaction', backref='user', lazy=True)

#     def set_password(self, password):
#         self.password = generate_password_hash(password)

#     def check_password(self, password):
#         return check_password_hash(self.password, password)

# class RegistrationForm(FlaskForm):
#     username = StringField('Username', [validators.InputRequired()])
#     email = StringField('Email', [validators.Email(), validators.InputRequired()])
#     password = PasswordField('Password', [validators.InputRequired(), validators.EqualTo('confirm', message='Passwords must match')])
#     confirm = PasswordField('Repeat Password')
#     submit = SubmitField('Register')

# class LoginForm(FlaskForm):
#     username = StringField('Username', [validators.InputRequired()])
#     password = PasswordField('Password', [validators.InputRequired()])
#     submit = SubmitField('Login')

# class Category(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), unique=True, nullable=False)
#     transactions = db.relationship('Transaction', backref='category', lazy=True)


# @app.route('/add_transaction', methods=['POST'])
# def add_transaction():
#     data = request.json
#     new_transaction = Transaction(amount=data['amount'], description=data['description'], user_id=session['user_id'])
#     # new_transaction = Transaction(amount=data['amount'], description=data['description'])
#     db.session.add(new_transaction)
#     db.session.commit()
#     return jsonify({"message": "Transaction added successfully!"}), 201

# @app.route('/get_transactions', methods=['GET'])
# def get_transactions():
#     transactions = Transaction.query.filter_by(user_id=session['user_id']).order_by(Transaction.date.desc()).limit(10).all()
#     transactions_data = [
#         {"id": t.id, "date": t.date.strftime('%Y-%m-%d %H:%M:%S'), "amount": t.amount, "description": t.description}
#         for t in transactions
#     ]
#     return jsonify(transactions_data)

# @app.route('/dashboard', methods=['GET', 'POST'])
# def dashboard():
#     if request.method == 'POST':
#         data = request.form
#         transaction_date = datetime.strptime(data['transaction_date'], "%Y-%m-%d").date()
#         new_transaction = Transaction(
#             date=transaction_date,
#             amount=data['amount'],
#             description=data['description'],
#             category_id=data['category'],
#             user_id=session['user_id']
#         )
#         db.session.add(new_transaction)
#         db.session.commit()
#         return redirect(url_for('dashboard'))

#     transactions = Transaction.query.filter_by(user_id=session['user_id']).order_by(Transaction.date.desc()).limit(10).all()
#     categories = Category.query.all()

#     # Filter the top_expenses by user_id
#     top_expenses = db.session.query(
#         Category.name, func.sum(Transaction.amount).label('total')
#     ).join(Transaction).filter(Transaction.user_id == session['user_id']).group_by(Category.name).order_by(
#         func.sum(Transaction.amount).desc()
#     ).limit(3).all()

#     # Retrieve monthly totals
#     monthly_totals_raw = db.session.query(
#         extract('year', Transaction.date).label('year'),
#         extract('month', Transaction.date).label('month'),
#         func.sum(Transaction.amount).label('total')
#     ).filter_by(user_id=session['user_id']).group_by('year', 'month').all()

#     # Convert raw monthly totals to a more suitable format
#     monthly_totals = [{"month": calendar.month_abbr[item.month], "year": item.year, "total_amount": item.total} for item in monthly_totals_raw]

#     return render_template('dashboard.html', transactions=transactions, categories=categories, top_expenses=top_expenses, monthly_totals=monthly_totals)

# @app.route('/api/total_spending_last_24h', methods=['GET'])
# def total_spending_last_24h():
#     one_day_ago = datetime.utcnow() - timedelta(days=1)
#     total = db.session.query(func.sum(Transaction.amount)).filter(Transaction.date > one_day_ago, Transaction.user_id == session['user_id']).scalar()
#     return jsonify({"total_spending": total or 0})

# @app.route('/register', methods=['GET', 'POST'])
# def register():
#     form = RegistrationForm()
#     if form.validate_on_submit():
#         user = User(username=form.username.data, email=form.email.data)
#         user.set_password(form.password.data) # Updated this line
#         db.session.add(user)
#         db.session.commit()
#         flash('You are now registered!')
#         return redirect(url_for('login'))
#     return render_template('register.html', form=form)

# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     form = LoginForm()
#     if form.validate_on_submit():
#         user = User.query.filter_by(username=form.username.data).first()
#         if user and user.check_password(form.password.data):
#             session['user_id'] = user.id
#             flash('Logged in successfully.')
#             return redirect(url_for('dashboard'))
#         flash('Invalid username or password.')
#     return render_template('login.html', form=form)

# @app.route('/logout')
# def logout():
#     session.pop('user_id', None)
#     return redirect(url_for('login'))

# @app.before_request
# def require_login():
#     allowed_routes = ['login', 'register']
#     if request.endpoint not in allowed_routes and 'user_id' not in session:
#         return redirect(url_for('login'))

# def get_monthly_totals(user_id):
#     monthly_totals = db.session.query(
#         extract('year', Transaction.date).label('year'),
#         extract('month', Transaction.date).label('month'),
#         func.sum(Transaction.amount).label('total')
#     ).filter_by(user_id=user_id).group_by('year', 'month').all()
#     return monthly_totals

# def calculate_trends(monthly_totals):
#     trends = []
#     for i in range(1, len(monthly_totals)):
#         previous_month = monthly_totals[i-1]
#         current_month = monthly_totals[i]

#         difference = current_month.total - previous_month.total
#         if difference > 0:
#             trend = 'Upward'
#         elif difference < 0:
#             trend = 'Downward'
#         else:
#             trend = 'Stable'

#         trends.append({
#             'year': current_month.year,
#             'month': current_month.month,
#             'trend': trend,
#             'difference': difference
#         })
#     return trends


# if __name__ == "__main__":
#     app.run(debug=True)