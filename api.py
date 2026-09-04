from flask import Flask, request, redirect, url_for, flash, render_template, render_template_string, jsonify, Blueprint
from database import db, Firma, Zamestnanec
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

# Vytvorenie Blueprintu s názvom 'api'
api_bp = Blueprint('api', __name__)

@api_bp.route('/api/posledna-firma')
def posledna_firma():
    # Vytiahne úplne poslednú pridanú firmu z databázy
    firma = db.session.query(Firma).order_by(Firma.id.desc()).first()
    if firma:
        # Vráti ID a názov naformátovaný rovnako ako metóda __str__
        return jsonify({'id': firma.id, 'nazov': f"{firma.nazov} ({firma.typ.value})"})
    return jsonify({})

@api_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        heslo = request.form.get('heslo')
        
        user = Zamestnanec.query.filter_by(email=email).first()
        # Werkzeug skontroluje zadané heslo voči hashu v DB
        if user and check_password_hash(user.heslo_hash, heslo):
            login_user(user)
            return redirect(url_for('admin.index'))
        else:
            flash('Nesprávny e-mail alebo heslo.', 'danger')

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head><title>Prihlásenie</title><link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css"></head>
    <body class="bg-light d-flex align-items-center" style="height: 100vh;">
        <div class="container" style="max-width: 400px;">
            <div class="card shadow-sm">
                <div class="card-body">
                    <h3 class="text-center mb-4">IJaV Systém</h3>
                    {% with messages = get_flashed_messages(with_categories=true) %}
                      {% if messages %}{% for category, message in messages %}<div class="alert alert-{{ category }}">{{ message }}</div>{% endfor %}{% endif %}
                    {% endwith %}
                    <form method="POST">
                        <div class="form-group"><label>E-mail</label><input type="email" name="email" class="form-control" required autofocus></div>
                        <div class="form-group"><label>Heslo</label><input type="password" name="heslo" class="form-control" required></div>
                        <button type="submit" class="btn btn-primary btn-block">Prihlásiť sa</button>
                    </form>
                </div>
            </div>
        </div>
    </body>
    </html>
    ''')

@api_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('api.login'))

@api_bp.route('/zmena-hesla', methods=['GET', 'POST'])
@login_required
def zmena_hesla():
    if request.method == 'POST':
        stare = request.form.get('stare_heslo')
        nove = request.form.get('nove_heslo')
        
        if check_password_hash(current_user.heslo_hash, stare):
            current_user.heslo_hash = generate_password_hash(nove)
            db.session.commit()
            flash('Heslo bolo úspešne zmenené.', 'success')
            return redirect(url_for('admin.index'))
        else:
            flash('Nesprávne aktuálne heslo.', 'danger')

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head><title>Zmena hesla</title><link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css"></head>
    <body class="bg-light p-5">
        <div class="container" style="max-width: 400px;">
            <h4 class="mb-3">Zmena hesla</h4>
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}{% for category, message in messages %}<div class="alert alert-{{ category }}">{{ message }}</div>{% endfor %}{% endif %}
            {% endwith %}
            <form method="POST" class="bg-white p-4 border rounded">
                <div class="form-group"><label>Aktuálne heslo</label><input type="password" name="stare_heslo" class="form-control" required></div>
                <div class="form-group"><label>Nové heslo</label><input type="password" name="nove_heslo" class="form-control" required></div>
                <button type="submit" class="btn btn-success btn-block">Zmeniť heslo</button>
                <a href="/" class="btn btn-link btn-block">Späť do systému</a>
            </form>
        </div>
    </body>
    </html>
    ''')
