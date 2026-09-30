from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from database import db, Firma, Zakazka,  TypFirmy,  StavZakazky
from flask import Flask, request, redirect, url_for, flash, render_template, render_template_string, jsonify, Blueprint
from markupsafe import Markup


#formatuje datum pre vsetko
def date_formatter(view, context, model, name):    
    value = getattr(model, name)
    if value:            
        return value.strftime('%d.%m.%Y')
    return ''

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
    #zakaze maxzanie poloziek
    can_delete = False
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


# 2. Hlavné nastavenie pre Zákazku
class ZakazkaView(SecureView):
    # Pomenujeme šablónu podľa tabuľky
    list_template = 'admin/zakazka_filter_list.html'
    
    #vykreaslenie podmienky
    def render(self, template, **kwargs):
        #Stav zakazky
        kwargs['status_options'] = StavZakazky
        kwargs['current_status'] = request.args.get('status', '')
        
        #firma
        # 1. Načítame zoznam všetkých firiem pre dropdown
        # Poznamka: Ak ich máš tisíce, odporúča sa zoradiť podľa názvu
        kwargs['firmy'] = Firma.query.filter_by(typ='ZAKAZNIK').order_by(Firma.nazov.asc()).all()
        kwargs['current_firma_id'] = request.args.get('firma_id', '')
        
        # Odovzdáme všetky aktuálne URL args, aby sme ich v HTML vedeli uchovať
        kwargs['request_args'] = request.args
        return super().render(template, **kwargs)

    #vyber zakazky podla podmienky
    def get_query(self):
        query = super().get_query()
        
        #filter pre enum stav
        status_val = request.args.get('status')
        if status_val:
            query = query.filter(Zakazka.stav_zakazky == status_val)
            
        # 2. Filter pre Cudzí kľúč (Firma)
        id_firma = request.args.get('firma_id')
        if id_firma:
            query = query.filter(Zakazka.id_firma == id_firma)
        return query

    #kolko takych zakazok mam
    def get_count_query(self):
        query = super().get_count_query()
        status_val = request.args.get('status')
        if status_val:
            query = query.filter(Zakazka.stav_zakazky == status_val)
        id_firma = request.args.get('firma_id')
        if id_firma:
            query = query.filter(Zakazka.id_firma == id_firma)            
        return query
    
    
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

    # vytvorenie zakazky a edit
    
    def get_klienti():
        return Firma.query.filter_by(typ='ZAKAZNIK').all()
    
    create_template = 'admin/zakazka_create.html'
    edit_template = 'admin/zakazka_edit.html'
    
    form_widget_args = {
        'zamestnanec': {'required': False},
        'ijav_pobocka': {'required': False},
        'klient': {'required': False}
    }
    
    form_columns = [
        'klient',
        'ijav_pobocka',        
        'popis',        
        'stav_zakazky',
        'typ_zakazky',
        'termin_dokoncenia'    
    ]

    form_excluded_columns = ('polozky','zamestnanec')
    
    # 4. Tvoje pôvodné vyfiltrovanie roletiek vo formulári Zákazky
    form_args = {
        'ijav_pobocka': {
            'query_factory': lambda: db.session.query(Firma).filter(Firma.typ == TypFirmy.IJAV)
        }
    }
    
    def create_form(self, obj=None):
        form = super().create_form(obj)
        
        # Prístup priamo k políčku klient vo vytvorenom WTForme
        if hasattr(form, 'klient'):
            form.klient.query_factory = lambda: db.session.query(Firma).filter(
                Firma.typ == 'ZAKAZNIK'                
            ).all()
            form.klient.allow_blank = True
            form.klient.blank_text = '-- Vyberte klienta --'
            
            # Pri otvorení nového formulára vynútiť prázdnu hodnotu
            if request.method == 'GET':
                form.klient.data = None
                
        return form

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
        'akcie': _akcie_formatter,
        'termin_dokoncenia': date_formatter
    }



