import os
import sqlite3
from dotenv import load_dotenv
from flask import Flask, request, redirect, url_for, flash, render_template, render_template_string, jsonify, Blueprint
from flask_admin import Admin, AdminIndexView
from flask_admin.menu import MenuLink
from flask_admin.contrib.sqla import ModelView
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_admin.model.form import InlineFormAdmin
from flask_babel import Babel

from sqlalchemy import event
from sqlalchemy.engine import Engine
from markupsafe import Markup

from werkzeug.security import generate_password_hash
from wtforms import PasswordField

# Importujeme inštanciu databázy a modely z nášho database.py
from database import db, Zamestnanec, Firma, Zakazka, Polozka, ZurnalCeny, ZurnalStavy, Pokladna, TypFirmy, Ucet, init_languages, Jazyk, TypPohybu

from api import api_bp

app = Flask(__name__)

# Nastavenia ťaháme z operačného systému / .env súboru
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-bezpecnostny-kluc')
# Všimni si, že SQLAlchemy hľadá SQLALCHEMY_DATABASE_URI, my mu priradíme náš DATABASE_URL z .env
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///ijav.db')
app.config['BABEL_DEFAULT_LOCALE'] = 'sk'
app.config['FLASK_ADMIN_SWATCH'] = 'flatly'

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
#  zoznam secure view podedenych po Modelviews
###########################################


# 1. Zabezpečený dashboard
class SecureAdminIndex(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('api.login', next=request.url))

# 2. Základná trieda pre bežné tabuľky (pre všetkých prihlásených)
class SecureView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        # Presmeruje na login a cez 'next' si zapamätá, kam používateľ smeroval
        return redirect(url_for('api.login', next=request.url))

# 3. Trieda pre citlivé tabuľky (iba Admin)
class AdminOnlyView(SecureView):  # Dedi zo SecureView -> zdedí aj inaccessible_callback
    def is_accessible(self):
        # Skontroluje prihlásenie zo SecureView + overí admin rolu
        return super().is_accessible() and getattr(current_user, 'admin', False)


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

# 2. Hlavné nastavenie pre Zákazku
class ZakazkaView(SecureView):
    create_modal = False
    edit_modal = False
    
    column_default_sort = ('id', True)
        
    # 1. Počet záznamov na jednu stránku (predvolené býva 20)
    page_size = 50  # Alebo si nastav 10, 25, 100 podľa potreby

    # 2. Umožní používateľovi meniť počet zobrazených položiek priamo v UI
    can_set_page_size = True

    # 3. Zoznam stĺpcov, podľa ktorých sa bude dať filtrovať (objaví sa tlačidlo "Add Filter")
    column_filters = (
        'ijav_pobocka',
        'klient',
        'popis',
        'stav_zakazky',
        'typ_zakazky',
        'termin_dokoncenia'
    )

    # 1. Zobrazíme v tabuľke stĺpce + náš nový stĺpec 'akcie'
    column_list = ('id','popis', 'ijav_pobocka', 'klient', 'stav_zakazky', 'typ_zakazky', 'termin_dokoncenia', 'akcie')

    # 2. Pekné slovenské názvy
    column_labels = {
        'id': 'ID',
        'ijav_pobocka': 'Pobočka',
        'klient': 'Klient',
        'stav_zakazky': 'Stav zákazky',
        'typ_zakazky': 'Typ zakázky',
        'termin_dokoncenia': 'Termín',
        'akcie': 'Položky'
    }

    # 2. Pri vytvorení nového záznamu priradíme ID aktuálne prihláseného používateľa
    def on_model_change(self, form, model, is_created):
        if is_created and current_user and current_user.is_authenticated:
            model.id_zamestnanca = current_user.id
            
        super().on_model_change(form, model, is_created)

    # 3. Tlačidlo, ktoré vygeneruje odkaz na samostatnú stránku položiek
    def _akcie_formatter(view, context, model, name):
        url = url_for('polozka.index_view', zakazka_id=model.id)
        pocet_poloziek = len(model.polozky) if model.polozky else 0
        return Markup(f'<a class="btn btn-xs btn-primary" href="{url}">📋 Zobraziť položky ({pocet_poloziek})</a>')

    column_formatters = {
        'akcie': _akcie_formatter
    }

    # 4. Tvoje pôvodné vyfiltrovanie roletiek vo formulári Zákazky
    form_args = {
        'ijav_pobocka': {
            'query_factory': lambda: db.session.query(Firma).filter(Firma.typ == TypFirmy.IJAV)
        },
        'klient': {
            'query_factory': lambda: db.session.query(Firma).filter(Firma.typ == TypFirmy.ZAKAZNIK),
            'description': Markup(
                '<button id="btn-nova-firma" class="btn btn-sm btn-success" style="margin-top: 5px;">'
                '➕ Vytvoriť novú firmu</button>'
            )
        }
    }
    
    form_widget_args = {
        'zamestnanec': {'required': False},
        'ijav_pobocka': {'required': False},
        'klient': {'required': False}
    }
    
    form_columns = [
        'ijav_pobocka',
        'popis',
        'klient',
        'stav_zakazky',
        'typ_zakazky',
        'termin_dokoncenia'    
    ]

    
    form_excluded_columns = ('polozky','zamestnanec')

#zobrazenie poloziek iba pre zakazku
class PolozkaView(SecureView):
    # ==========================================
    # 1. BEZPEČNOSŤ A VIDITEĽNOSŤ (MENU)
    # ==========================================
    def is_visible(self):
        # Zabezpečí, že sa záložka "Položky" neukáže v hornom menu
        return False
        
    column_default_sort = ('id', True)
    
    # ==========================================
    # 2. ZOBRAZENIE (TABUĽKA - ZOZNAM POLOŽIEK)
    # ==========================================
    # Ktorá šablóna sa použije na vykreslenie celej stránky
    list_template = 'polozka_list.html'

    # PRESNÝ zoznam stĺpcov, ktoré chceš v tabuľke vidieť (týmto zaručíš, 
    # že tam nebude strašiť stĺpec Zákazka ani iné nechcené relácie)
    column_list = (
        'id',
        'popis',
        'typ_prekladu',
        'jazyk_z',
        'jazyk_do',
        'cena',
        'naklady',
        'stav_platby',
        'stav_naklady',
        'dodavatel'
    )

    # Ako sa budú stĺpce volať v hlavičke tabuľky a vo formulároch
    column_labels = {
        'popis': 'Popis',
        'typ_prekladu': 'Typ prekladu',
        'jazyk_z': 'Z jazyka',
        'jazyk_do': 'Do jazyka',
        'cena': 'Predajná cena (€)',
        'naklady': 'Náklady (€)',
        'stav_platby': 'Stav platby',
        'stav_naklady': 'Stav náklady',
        'dodavatel': 'Dodávateľ',
        'zakazka': 'Zákazka'
    }    

    # ==========================================
    # 3. EDITÁCIA A PRIDÁVANIE (FORMULÁRE)
    # ==========================================
    # Otvárať formuláre v pop-up okne namiesto novej stránky
    create_modal = True
    edit_modal = True

    # Obmedzenia pre konkrétne polia vo formulári (roletky)
    form_args = {
        'dodavatel': {
            'query_factory': lambda: db.session.query(Firma).filter(Firma.typ == TypFirmy.DODAVATEL)
        }
    }

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
        return super().render(template, **kwargs)

    def on_form_prefill(self, form, id):
        """Ovplyvňuje formulár (Create): Predvyplní neviditeľné/viditeľné pole pri otvorení okna."""
        zakazka_id = request.args.get('zakazka_id')
        if zakazka_id and hasattr(form, 'zakazka'):
            form.zakazka.data = db.session.get(Zakazka, int(zakazka_id))
            
    def on_model_change(self, form, model, is_created):
        """Ovplyvňuje databázu (Save): Tesne pred uložením doplní autora."""
        if is_created and not model.id_zamestnanca:
            model.id_zamestnanca = current_user.id
        super().on_model_change(form, model, is_created)

# 3. Vylepšenie pre Firmy (otváranie v rýchlom vyskakovacom okne)
class FirmaView(SecureView):
    create_modal = True
    edit_modal = True
    
    column_labels = {
        'nazov': 'Názov firmy',
        'adresa': 'Adresa',
        'zip_code': 'PSČ',
        'mesto': 'Mesto',
        'ico': 'IČO',
        'dic': 'DIČO',
        'typ': 'Typ firmy'
    }    

    column_filters = ['nazov', 'typ']
    
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
        
    column_list = ['popis', 'pohyb', 'hodnota', 'cislo_dokladu', 'timestamp']

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
    )
)

# Pridanie tabuliek do Admin panelu, aby sme ich mohli klikať
admin.add_view(FirmaView(Firma, db.session, name='Firmy'))
admin.add_view(ZakazkaView(Zakazka, db.session, name='Zákazky'))
admin.add_view(PolozkaView(Polozka, db.session, name='Položky'))

admin.add_view(ZamestnanecView(Zamestnanec, db.session, name='Zamestanci'))
admin.add_view(PokladnaView(Pokladna, db.session,name='Pokladňa'))
admin.add_view(UcetView(Ucet, db.session, name='Účty'))
admin.add_view(SecureView(Jazyk, db.session, name='Jazyky'))

admin.add_link(UserMenuLink(name='', url='#', class_name='pull-right float-right'))
admin.add_link(MenuLink(name='🔑 Zmena hesla', url='/zmena-hesla', class_name='pull-right float-right'))
admin.add_link(MenuLink(name='🚪 Odhlásiť sa', url='/logout', class_name='pull-right float-right'))

# Vytvorenie databázy pri prvom spustení
with app.app_context():
    db.create_all()
    init_languages(db.session)
    print("Databáza bola úspešne vytvorená!")
    


if __name__ == '__main__':
    # Spustenie vývojového servera
    app.run(debug=True)