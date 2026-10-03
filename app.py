import os
import sqlite3
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from flask import Flask, request, redirect, url_for, flash, render_template, render_template_string, jsonify, Blueprint
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.menu import MenuLink
from flask_admin.contrib.sqla import ModelView
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_admin.model.form import InlineFormAdmin
from flask_admin.theme import Bootstrap4Theme

from flask_babel import Babel
from flask_migrate import Migrate

from sqlalchemy import event, func
from sqlalchemy.engine import Engine

from werkzeug.security import generate_password_hash
from wtforms import PasswordField, TextAreaField, HiddenField, StringField, SelectField

# Importujeme inštanciu databázy a modely z nášho database.py
from database import db, Zamestnanec, Firma, Zakazka, Polozka, ZurnalCeny, ZurnalStavy, Pokladna, TypFirmy, Ucet, init_languages, Jazyk, TypPohybu, StavZakazky

from views import ZakazkaView, SecureView, AdminIndexView, AdminOnlyView, SecureAdminIndex, date_formatter

from api import api_bp

app = Flask(__name__)

# Nastavenia ťaháme z operačného systému / .env súboru
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-bezpecnostny-kluc')
# Všimni si, že SQLAlchemy hľadá SQLALCHEMY_DATABASE_URI, my mu priradíme náš DATABASE_URL z .env
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///ijav.db')
app.config['BABEL_DEFAULT_LOCALE'] = 'sk'

babel = Babel(app)

# 1. Inicializácia databázy
db.init_app(app)

# 2. Registrácia externých endpointov (Blueprints)
app.register_blueprint(api_bp)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Spustí sa LEN vtedy, ak ide o SQLite databázu
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# manazovanie loginov a current_user
login_manager = LoginManager()
login_manager.init_app(app)
# Ak nie je používateľ prihlásený, presmeruje ho na túto cestu:
login_manager.login_view = 'api.login' 

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Zamestnanec, int(user_id))


###########################################
#  zoznam views
###########################################

class UserMenuLink(MenuLink):
    def get_url(self):
        # Odkaz nebude nikam viesť (iba indikátor)
        return "#"

    # Toto prepíše text tlačidla dynamicky pri každom načítaní stránky
    def is_accessible(self):
        if current_user.is_authenticated:
            meno = f"{getattr(current_user, 'meno', '')} {getattr(current_user, 'priezvisko', '')}".strip()
            self.name = f"👤 {meno if meno else current_user.email}"
        return True

# 1. Nastavenie pre vnorenú Položku (ukáže sa vnútri Zákazky)
class PolozkaInline(InlineFormAdmin):
    form_args = {
        'dodavatel': {
            # V roletke Dodávateľ ukáž len firmy typu DODAVATEL
            'query_factory': lambda: db.session.query(Firma).filter(Firma.typ == TypFirmy.DODAVATEL)
        }
    }

#zobrazenie poloziek iba pre zakazku
class PolozkaView(SecureView):
    # ==========================================
    # 3. EDITÁCIA A PRIDÁVANIE (FORMULÁRE)
    # ==========================================
    # Otvárať formuláre v pop-up okne namiesto novej stránky
    create_modal = True
    #edit_modal = True
        
    # Pre modálne okná MUSÍŠ použiť premenné s '_modal_':
    create_modal_template = 'admin/polozka_create.html'
    
    can_edit = True          # Odstráni tlačidlo/ikonu Edit z riadku
    
    # ==========================================
    # 1. BEZPEČNOSŤ A VIDITEĽNOSŤ (MENU)
    # ==========================================
    def is_visible(self, *args, **kwargs):
        return False
        
    column_default_sort = ('id', True)

    # ==========================================
    # 2. ZOBRAZENIE (TABUĽKA - ZOZNAM POLOŽIEK)
    # ==========================================
    # Ktorá šablóna sa použije na vykreslenie celej stránky
    list_template = 'admin/polozka_list.html'

    # PRESNÝ zoznam stĺpcov, ktoré chceš v tabuľke vidieť (týmto zaručíš, 
    # že tam nebude strašiť stĺpec Zákazka ani iné nechcené relácie)
    column_list = (
        'dodavatel',        
        'popis',
        'typ_prekladu',
        'jazyky_prekladu',        
        'cena',
        'naklady',
        'stav_platby',
        'stav_naklady'        
    )

    column_editable_list = ['popis', 'stav_platby', 'stav_naklady']

    # Ako sa budú stĺpce volať v hlavičke tabuľky a vo formulároch
    column_labels = {
        'popis': 'Popis',
        'typ_prekladu': 'Typ prekladu',
        'jazyk_prekladu': 'Preklad',        
        'cena': 'Predajná cena (€)',
        'naklady': 'Náklady (€)',
        'stav_platby': 'Stav platby',
        'stav_naklady': 'Stav náklady',
        'dodavatel': 'Dodávateľ'        
    }    


    #### nastavenie formulara na edit
    form_columns = [
        'popis', 'dodavatel',
        'typ_prekladu', 'jazyk_z', 'jazyk_do', 'cena', 'naklady',
        'stav_platby', 'typ_platby', 'stav_naklady'
    ]
    
    form_extra_fields = {
        'meno_zakazky': StringField('Zákazka', render_kw={'readonly': True})
    }
    
    # Obmedzenia pre konkrétne polia vo formulári (roletky)
    form_args = {
        'dodavatel': {
            'query_factory': lambda: db.session.query(Firma).filter(Firma.typ == TypFirmy.DODAVATEL)
        }
    }
            
            
    # Automatické predvyplnenie zákazky z URL parametra zakazka_id
    def create_form(self, obj=None):
        form = super().create_form(obj)                
        
        if hasattr(form, 'dodavatel'):
            
            form.dodavatel.query_factory = lambda: db.session.query(Firma).filter(
                Firma.typ == 'DODAVATEL'
            ).all()
            form.dodavatel.allow_blank = True
            form.dodavatel.blank_text = '-- Vyberte dodávateľa --'
            
            if request.method == 'GET':
                form.dodavatel.data = None
        
        # Získanie zakazka_id z URL
        return_url = request.args.get('url') or request.referrer or ''
        parsed_url = urlparse(return_url)
        parsed_query = parse_qs(parsed_url.query)
        zakazka_id = parsed_query.get('zakazka_id')[0]
        
        zakazka = db.session.get(Zakazka, zakazka_id)            
        # Nastavíme len textový názov do formulára
        form.meno_zakazky = str(zakazka)
                
        return form    

    # ==========================================
    # 4. LOGIKA PODĽA URL A PRÁCA S DATABÁZOU
    # ==========================================
    def get_query(self):
        """Ovplyvňuje zobrazenie: Filtruje SQL dotaz pre tabuľku."""
        query = super().get_query()
        zakazka_id = request.args.get('zakazka_id')
        if zakazka_id:
            query = query.filter(Polozka.id_zakazky == zakazka_id)
        return query

    def render(self, template, **kwargs):
        """Ovplyvňuje zobrazenie: Posiela premenné (zákazku) do HTML šablóny."""
        zakazka_id = request.args.get('zakazka_id')
        if zakazka_id:
            kwargs['aktualna_zakazka'] = db.session.get(Zakazka, int(zakazka_id))
            kwargs['suma_cena'] = db.session.query(func.sum(Polozka.cena)).filter(Polozka.id_zakazky == zakazka_id).scalar() or 0
            kwargs['suma_naklady'] = db.session.query(func.sum(Polozka.naklady)).filter(Polozka.id_zakazky == zakazka_id).scalar() or 0
        return super().render(template, **kwargs)

    def on_form_prefill(self, form, id):
        """Ovplyvňuje formulár (Create): Predvyplní neviditeľné/viditeľné pole pri otvorení okna."""
        zakazka_id = request.args.get('zakazka_id')
        if zakazka_id and hasattr(form, 'zakazka'):
            form.zakazka.data = db.session.get(Zakazka, int(zakazka_id))
            
    def on_model_change(self, form, model, is_created):
        """Ovplyvňuje databázu (Save): Tesne pred uložením doplní autora."""
        return_url = request.args.get('url')
        parsed_url = urlparse(return_url)
        parsed_query = parse_qs(parsed_url.query)
        
        if parsed_query:
            zakazka_id = parsed_query['zakazka_id'][0]
            model.id_zakazky = zakazka_id

        if is_created and not model.id_zamestnanca:
            model.id_zamestnanca = current_user.id
        super().on_model_change(form, model, is_created)

# 3. Vylepšenie pre Firmy (otváranie v rýchlom vyskakovacom okne)
class FirmaView(SecureView):
    create_modal = True
    edit_modal = True
    
    create_modal_template = 'admin/firma_create.html'
    #edit_modal_template = 'admin/firma_edit.html'
    
    column_labels = {
        'nazov': 'Názov firmy',
        'adresa': 'Adresa',
        'zip_code': 'PSČ',
        'mesto': 'Mesto',
        'ico': 'IČO',
        'dic': 'DIČO',
        'typ': 'Typ firmy'
    }    

    column_formatters = {
        # m.typ_firmy.value vráti "IJaV", "Zákazník", "Dodávateľ"
        'typ': lambda v, c, m, p: m.typ.value if m.typ else ''
    }

    #column_filters = ['nazov', 'typ']
    
    list_template = 'admin/firma_filter_list.html'
    
        #vykreaslenie podmienky
    def render(self, template, **kwargs):
        #Stav zakazky
        kwargs['typ_firmy'] = TypFirmy
        kwargs['current_firma_typ'] = request.args.get('firma_typ', '')
                
        # Odovzdáme všetky aktuálne URL args, aby sme ich v HTML vedeli uchovať
        kwargs['request_args'] = request.args
        return super().render(template, **kwargs)
    
    def get_query(self):
        """Ovplyvňuje zobrazenie: Filtruje SQL dotaz pre tabuľku."""
        query = super().get_query()
        firma_typ = request.args.get('firma_typ')
        if firma_typ:
            query = query.filter(Firma.typ == firma_typ)
        
        firma_name = request.args.get('firma-name-filter')
        if firma_name:
            query = query.filter(Firma.id == firma_name)
            
        return query
    
    # Nový vlastný endpoint pre AJAX vytváranie
    @expose('/ajax_create/', methods=['POST'])
    def ajax_create(self):
        # 1. Vytvoríme formulár pre tento model
        form = self.create_form()

        # 2. Skontrolujeme validáciu
        if form.validate():
            try:
                # 1. Vytvoríme novú inštanciu modelu z formulára
                model = self.model()
                form.populate_obj(model)

                # 2. Pridáme do session a spravíme commit
                self.session.add(model)
                self.session.commit()  # SQLAlchemy tu automaticky doplní `model.id`

                # 3. Vrátime vygenerované ID a názov
                return jsonify({
                    'success': True,
                    'id': model.id,
                    'nazov': getattr(model, 'nazov', str(model))
                })

            except Exception as ex:
                self.session.rollback()
                return jsonify({'success': False, 'error': str(ex)}), 400
        
        else:
            # Ak neprešla validácia WTForms (napr. chýbajúce povinné pole)
            return jsonify({'success': False, 'errors': form.errors}), 400
    
    @app.route('/api/firmy/search')
    def search_firmy():
        q = request.args.get('q', '')
        firmy = Firma.query.filter(Firma.nazov.ilike(f'%{q}%')).limit(15).all()
        return jsonify([{'id': f.id, 'text': f.nazov} for f in firmy])

    
# vylepesniue a texty pre ucet
class UcetView(AdminOnlyView):
    create_modal = True
    edit_modal = True
    
    # Pekné slovenské názvy pre tabuľku aj formulár
    column_labels = {
        'id': 'ID Účtu',
        'nazov': 'Názov účtu / Pokladne',
        'banka': 'Banka / Inštitúcia',
        'cislo_uctu': 'Číslo účtu (IBAN)'
    }

    # Voliteľné: Nápovedné texty pod políčka vo formulári
    column_descriptions = {
        'nazov': 'Napr. Hlavný firemný účet alebo Príručná pokladňa',
        'cislo_uctu': 'Vo formáte SK00 0000 0000 0000 0000 0000'
    }
    
class ZamestnanecView(AdminOnlyView): # Prípadne AdminOnlyView, ak to tak máš
    
    create_modal = True
    edit_modal = True
    
    # 1. Kto tam môže vojsť (bezpečnosť)
    def is_accessible(self):
        return current_user.is_authenticated and current_user.admin

    # 2. Kto to vidí v hornom menu (viditeľnosť)
    def is_visible(self):
        return current_user.is_authenticated and current_user.admin
    
    # 1. Skryjeme zaheslované reťazce z hlavnej tabuľky
    column_exclude_list = ('heslo_hash',)
    
    # 2. Vyhodíme surové databázové pole z formulára
    form_excluded_columns = ('heslo_hash',)
    
    # 3. Pridáme vlastné pole, ktoré sa bude tváriť ako hviezdičkové heslo
    form_extra_fields = {
        'nove_heslo': PasswordField('Heslo (nechaj prázdne pre predvolené "Start123")')
    }

    # 4. Magická metóda, ktorá sa spustí tesne pred uložením do databázy
    def on_model_change(self, form, model, is_created):
        # Ak admin vyslovene napísal nejaké heslo, zahashujeme ho
        if form.nove_heslo.data:
            model.heslo_hash = generate_password_hash(form.nove_heslo.data)
            
        # Ak admin nevyplnil nič, ale tvorí sa NOVÝ zamestnanec, dáme dočasné
        elif is_created:
            model.heslo_hash = generate_password_hash('Start123')
            
        # Ak je to iba úprava (editácia) existujúceho a heslo ostalo prázdne,
        # neurobíme nič -> model si zachová svoje staré zahashované heslo v DB.

class PokladnaView(SecureView):
    create_modal = True
    edit_modal = True
        
    column_labels = {
        'zakazka_id': 'Zákazka',
        'Pohyb': 'Pohyb',
        'Hodnota': 'Hodnota',
        'Popis': 'Popis',
        'cislo_dokladu': 'Číslo dokladu',
        'ucet': 'Účet'        
    }
        
    column_list = ['zakazka', 'popis', 'pohyb', 'hodnota', 'timestamp']

    # Alebo povieš, čo jediné z tabuľky vynechať:
    column_exclude_list = ['id_zamestnanca']
    
    form_columns = ['zakazka', 'pohyb', 'hodnota', 'cislo_dokladu', 'popis', 'ucet']
    
    # 1. Skryjeme pole z formulára, aby ho používateľ nemusel vyberať
    form_excluded_columns = ['id_zamestnanca', 'timestamp', 'parovy_zaznam', 'cislo_blocku']
    
    form_choices = {
        'pohyb': [
            (e.name, e.value) for e in TypPohybu if e != TypPohybu.KONTROLA
        ]
    }
    
    column_formatters = {
        'timestamp': date_formatter
    }
    
    def create_form(self, obj=None):
        form = super().create_form(obj)
        
        # Prístup priamo k políčku klient vo vytvorenom WTForme
        if hasattr(form, 'zakazka'):
            form.zakazka.allow_blank = True
            form.zakazka.blank_text = '-- Vyberte zakázku --'
            
            # Pri otvorení nového formulára vynútiť prázdnu hodnotu
            if request.method == 'GET':
                form.zakazka.data = None
                
        return form

    # 2. Pri vytvorení nového záznamu priradíme ID aktuálne prihláseného používateľa
    def on_model_change(self, form, model, is_created):
        if is_created and current_user and current_user.is_authenticated:
            model.id_zamestnanca = current_user.id            
        super().on_model_change(form, model, is_created)


# 3. Inicializácia Flask-Admin (zatiaľ necháme otvorené pre vývoj)
#admin = Admin(app, name='IJaV Kalkulačka')
admin = Admin(
    app, 
    name='IJaV Kalkulačka', 
    url='/',                      # Odstráni /admin/ a dá administráciu na hlavnú stránku (http://127.0.0.1:5000/)            
    index_view=SecureAdminIndex(    # Nastaví hlavnú stránku adminu
        name='Domov', 
        url='/',
        menu_class_name='d-none'
    ),
    theme=Bootstrap4Theme()
)

class JazykView(SecureView):
    create_modal = True
    edit_modal = True


# Pridanie tabuliek do Admin panelu, aby sme ich mohli klikať

admin.add_view(ZakazkaView(Zakazka, db.session, name='Zákazky'))
admin.add_view(PolozkaView(Polozka, db.session, name='Položky', endpoint='polozka'))
admin._menu.pop()
admin.add_view(FirmaView(Firma, db.session, name='Firmy', endpoint='firma'))
admin.add_view(PokladnaView(Pokladna, db.session,name='Pokladňa'))
admin.add_view(ZamestnanecView(Zamestnanec, db.session, name='Zamestanci'))
admin.add_view(UcetView(Ucet, db.session, name='Účty'))
admin.add_view(JazykView(Jazyk, db.session, name='Jazyky'))

admin.add_link(UserMenuLink(name='', url='#', class_name='pull-right float-right'))
admin.add_link(MenuLink(name='🔑 Zmena hesla', url='/zmena-hesla', class_name='pull-right float-right'))
admin.add_link(MenuLink(name='🚪 Odhlásiť sa', url='/logout', class_name='pull-right float-right'))


# Vytvorenie databázy pri prvom spustení
with app.app_context():
    db.create_all()
    init_languages(db.session)
    print("Databáza bola úspešne vytvorená!")
    #migrate = Migrate(app, db)
    #print("Databáza bola úspešne modifikovana!")
    

if __name__ == '__main__':
    # Spustenie vývojového servera
    app.run(debug=True)