import enum
from typing import Optional
from datetime import datetime, date, timezone
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session, object_session
from sqlalchemy import String, Integer, ForeignKey, Numeric, DateTime, Date, Boolean, Text, event, func
from flask_login import UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm.attributes import get_history

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# ==========================================
# 1. ENUMY
# ==========================================
class TypFirmy(enum.Enum):
    IJAV = "IJaV"
    ZAKAZNIK = "Zákazník"
    DODAVATEL = "Dodávateľ"

class StavZakazky(enum.Enum):
    NOVA = "Nová"
    V_RIESENI = "V riešení"
    DOKONCENA = "Dokončená"
    ZRUSENA = "Zrušená"

class TypZakazky(enum.Enum):
    PREKLAD = "Preklad"
    TLMOCENIE = "Tlmočenie"
    KOREKTURA = "Korektúra"

class StavPlatby(enum.Enum):
    NEZAPLATENA = "Nezaplatená"
    CASTOCNE = "Čiastočne zaplatená"
    ZAPLATENA = "Zaplatená"

class TypPlatby(enum.Enum):
    HOTOVOST = "Hotovosť"
    BANKA = "Prevod na účet"
    KARTA = "Platobná karta"

class StavNaklady(enum.Enum):
    NEVYPLATENE = "Nevyplatené"
    VYPLATENE = "Vyplatené dodávateľovi"

class TypPohybu(enum.Enum):
    PRIJEM = "Príjem"
    VYDAJ = "Výdaj"
    BANKA = "Banka (Vklad na účet)"
    KONTROLA = "Kontrola"

class AtributStav(enum.Enum):
    STAV_PLATBY = "stav_platby"
    STAV_NAKLADY = "stav_naklady"
    STAV_ZAKAZKY = "stav_zakazky"

class AtributCena(enum.Enum):
    CENA = "cena"
    NAKLADY = "naklady"
    
class TypPrekladu(enum.Enum):
    URADNY = "Úradný"
    NEURADNY = "Neúradný"


# ==========================================
# 2. ZÁKLADNÉ ČÍSELNÍKY A POUŽÍVATELIA
# ==========================================
class Firma(db.Model):
    __tablename__ = 'firma'

    id: Mapped[int] = mapped_column(primary_key=True)
    nazov: Mapped[str] = mapped_column(String(150), nullable=False)
    adresa: Mapped[str] = mapped_column(String(150), nullable=True)
    mesto: Mapped[str] = mapped_column(String(100), nullable=True)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=True)
    ico: Mapped[str] = mapped_column(String(10), nullable=True)
    dic: Mapped[str] = mapped_column(String(10), nullable=True)
    # Pridané nepovinné polia
    telefon: Mapped[str] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(120), nullable=True)
    typ: Mapped[TypFirmy] = mapped_column(nullable=False, default=TypFirmy.ZAKAZNIK)
    def __str__(self):
        return self.nazov

class Zamestnanec(UserMixin, db.Model):
    __tablename__ = 'zamestnanec'

    id: Mapped[int] = mapped_column(primary_key=True)
    meno: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    heslo_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    admin: Mapped[bool] = mapped_column(Boolean, default=False)

    def nastav_heslo(self, heslo: str):
        self.heslo_hash = generate_password_hash(heslo)

    def over_heslo(self, heslo: str) -> bool:
        return check_password_hash(self.heslo_hash, heslo)
    def __str__(self):
        return self.meno


class Jazyk(db.Model):
    __tablename__ = 'jazyk'

    id: Mapped[int] = mapped_column(primary_key=True)
    kod: Mapped[str] = mapped_column(String(10), unique=True, nullable=False) # ISO skratka (napr. SK, EN, JP)
    nazov: Mapped[str] = mapped_column(String(100), nullable=False)           # Názov (Slovenčina, Angličtina...)

    def __str__(self):
        return self.kod

# ==========================================
# 3. BIZNIS LOGIKA (ZÁKAZKY A POLOŽKY)
# ==========================================
class Zakazka(db.Model):
    __tablename__ = 'zakazka'

    id: Mapped[int] = mapped_column(primary_key=True)
    id_firma: Mapped[int] = mapped_column(ForeignKey('firma.id')) # IJaV pobočka
    id_zakaznika: Mapped[int] = mapped_column(ForeignKey('firma.id')) # Reálny klient
    id_zamestnanca: Mapped[int] = mapped_column(ForeignKey('zamestnanec.id'))
    
    popis: Mapped[str] = mapped_column(String(255), nullable=False)
    stav_zakazky: Mapped[StavZakazky] = mapped_column(default=StavZakazky.NOVA)
    typ_zakazky: Mapped[TypZakazky] = mapped_column(default=TypZakazky.PREKLAD)
    termin_dokoncenia: Mapped[date] = mapped_column(Date, nullable=True)

    # Relácie s explicitným určením cudzích kľúčov kvôli dvom spojeniam na tabuľku Firma
    zamestnanec: Mapped["Zamestnanec"] = relationship()
    polozky: Mapped[list["Polozka"]] = relationship(back_populates="zakazka", cascade="all, delete-orphan")
    
    
    # 1. PrimaryJoin pre IJaV pobočku
    ijav_pobocka: Mapped["Firma"] = relationship(
        primaryjoin="and_(Zakazka.id_firma == Firma.id, Firma.typ == 'IJAV')",
        foreign_keys=[id_firma]
    )

    # 2. PrimaryJoin pre Zákazníka
    klient: Mapped["Firma"] = relationship(
        primaryjoin="and_(Zakazka.id_zakaznika == Firma.id, Firma.typ == 'ZAKAZNIK')",
        foreign_keys=[id_zakaznika]        
    )        
    def __str__(self):
        return f"{self.popis}"
    


class Polozka(db.Model):
    __tablename__ = 'polozka'

    id: Mapped[int] = mapped_column(primary_key=True)
    id_zakazky: Mapped[int] = mapped_column(ForeignKey('zakazka.id'))
    id_zamestnanca: Mapped[int] = mapped_column(ForeignKey('zamestnanec.id'))
    id_dodavatel: Mapped[int] = mapped_column(ForeignKey('firma.id')) # Dodávateľ/Prekladateľ
    
    popis: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # NOVÉ STĹPCE PRE JAZYKY A TYP PREKLADU
    typ_prekladu: Mapped[TypPrekladu] = mapped_column(default=TypPrekladu.NEURADNY)
    id_jazyk_z: Mapped[int | None] = mapped_column(ForeignKey('jazyk.id'))
    id_jazyk_do: Mapped[int | None] = mapped_column(ForeignKey('jazyk.id'))
    
    cena: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    naklady: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    
    stav_platby: Mapped[StavPlatby] = mapped_column(default=StavPlatby.NEZAPLATENA)
    typ_platby: Mapped[TypPlatby] = mapped_column(default=TypPlatby.BANKA)
    stav_naklady: Mapped[StavNaklady] = mapped_column(default=StavNaklady.NEVYPLATENE)

    zakazka: Mapped["Zakazka"] = relationship(back_populates="polozky")    
    dodavatel: Mapped["Firma"] = relationship(
        primaryjoin="and_(Polozka.id_dodavatel == Firma.id, Firma.typ == 'DODAVATEL')",
        foreign_keys=[id_dodavatel]
    )
    
    id_jazyk_z: Mapped[Optional[int]] = mapped_column(ForeignKey('jazyk.id'))
    id_jazyk_do: Mapped[Optional[int]] = mapped_column(ForeignKey('jazyk.id'))
    
    jazyk_z: Mapped[Optional['Jazyk']] = relationship('Jazyk', foreign_keys=[id_jazyk_z])
    jazyk_do: Mapped[Optional['Jazyk']] = relationship('Jazyk', foreign_keys=[id_jazyk_do])
    
    def __str__(self):
        return f"{self.popis} ({self.typ_zakazky})"
    
    @property
    def jazyky_prekladu(self):
        return f"{self.jazyk_z} -> {self.jazyk_do}"

# ==========================================
# 4. ŽURNÁLY A POKLADŇA
# ==========================================
class ZurnalStavy(db.Model):
    __tablename__ = 'zurnal_stavy'

    id: Mapped[int] = mapped_column(primary_key=True)
    id_zakazky: Mapped[int | None] = mapped_column(ForeignKey('zakazka.id'))
    id_polozky: Mapped[int | None] = mapped_column(ForeignKey('polozka.id'))
    id_zamestnanca: Mapped[int] = mapped_column(ForeignKey('zamestnanec.id'))
    
    atribut: Mapped[AtributStav] = mapped_column(nullable=False)
    stara_hodnota: Mapped[str | None] = mapped_column(String(50))
    nova_hodnota: Mapped[str | None] = mapped_column(String(50))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class ZurnalCeny(db.Model):
    __tablename__ = 'zurnal_ceny'

    id: Mapped[int] = mapped_column(primary_key=True)
    id_zakazky: Mapped[int | None] = mapped_column(ForeignKey('zakazka.id'))
    id_polozky: Mapped[int | None] = mapped_column(ForeignKey('polozka.id'))
    id_zamestnanca: Mapped[int] = mapped_column(ForeignKey('zamestnanec.id'))
    
    atribut: Mapped[AtributCena] = mapped_column(nullable=False)
    stara_hodnota: Mapped[float | None] = mapped_column(Numeric(10, 2))
    nova_hodnota: Mapped[float | None] = mapped_column(Numeric(10, 2))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    
class Ucet(db.Model):
    __tablename__ = 'ucet'

    id: Mapped[int] = mapped_column(primary_key=True)
    nazov: Mapped[str] = mapped_column(String(100), nullable=False)  # napr. "Hlavný firemný účet", "Pokladničná rezerva"
    banka: Mapped[str] = mapped_column(String(100), nullable=False)  # napr. "Tatra banka", "SLSP"
    cislo_uctu: Mapped[str] = mapped_column(String(50), nullable=False) # IBAN

    def __str__(self):
        return f"{self.nazov} ({self.banka})"

class Pokladna(db.Model):
    __tablename__ = 'pokladna'

    id: Mapped[int] = mapped_column(primary_key=True)
    id_zamestnanca: Mapped[int] = mapped_column(ForeignKey('zamestnanec.id'))
    id_zakazky: Mapped[int] = mapped_column(ForeignKey('zakazka.id'))
    id_pokladna: Mapped[int | None] = mapped_column(ForeignKey('pokladna.id')) # Prepojenie záznamov
    
    # --- NOVE STĹPCE PRE DOKLADY A POČÍTADLO ---
    popis: Mapped[str] = mapped_column(String(255), nullable=False)
    cislo_dokladu: Mapped[int | None] = mapped_column(index=True)
    # Interné poradové číslo (napr. 1, 2, 3...), generované len pre hotovostné výdavky (VPD)
    cislo_blocku: Mapped[str | None] = mapped_column(String(50))
    # Číslo bločku z obchodu (externé číslo paragonu / eKasa UID / OKP kód)
    
    pohyb: Mapped[TypPohybu] = mapped_column(nullable=False)
    hodnota: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # ZMENA: Prepojenie na novú tabuľku Ucet namiesto prostého textu
    id_uctu: Mapped[int | None] = mapped_column(ForeignKey('ucet.id'))
    
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Self-referential relácia pre párovanie záznamov
    parovy_zaznam: Mapped["Pokladna"] = relationship(remote_side=[id])
    ucet: Mapped["Ucet"] = relationship()
    zakazka: Mapped["Zakazka"] = relationship()

# ==========================================
# 5. ŽURNÁLY EVENT LISTENERS
# ==========================================
def zurnal_text_event(mapper, connection, target):
    """
    Sleduje zmeny stavových polí na modeli Polozka 
    a vytvára záznamy v zurnal_stavy.
    """
    # 1. Zoznam sledovaných atribútov na Položke a ich párovanie na AtributStav Enum
    # 'stĺpec': (AtributEnum, CieľováTabuľka, typ_spracovania)
    sledovane_polia = {
        'stav_zakazky': (AtributStav.STAV_ZAKAZKY, ZurnalStavy, 'enum'),
        'stav_platby':  (AtributStav.STAV_PLATBY,  ZurnalStavy, 'enum'),
        'stav_naklady': (AtributStav.STAV_NAKLADY, ZurnalStavy, 'enum'),
        'cena':         (AtributCena.CENA,         ZurnalCeny,  'decimal'),
        'naklady':      (AtributCena.NAKLADY,      ZurnalCeny,  'decimal'),
    }
    # 2. Overenie prihláseného zamestnanca (id_zamestnanca je NOT NULL)
    user_id = None
    try:
        if current_user and current_user.is_authenticated:
            user_id = current_user.id
    except Exception:
        user_id = None

    # Ak nie je prihlásený žiaden používateľ (napr. skript na pozadí), 
    # nemôžeme zapísať do tabuľky, kde je id_zamestnanca povinné.
    if not user_id:
        return

    session = object_session(target)
    
    if target.id is None:
        session.flush()

    # Zistíme typ objektu a priradíme ID
    if isinstance(target, Zakazka):
        id_zakazky = target.id
        id_polozky = None
    elif isinstance(target, Polozka):
        id_polozky = target.id
        # Vytiahne id_zakazky z položky (ak existuje), inak vráti None
        id_zakazky = getattr(target, 'id_zakazky', None)
    else:
        id_zakazky = None
        id_polozky = None


    for attr_name, (enum_attr, TargetModel, typ_dat) in sledovane_polia.items():
        if not hasattr(target, attr_name):
            continue

        history = get_history(target, attr_name)
        if not history.added:
            continue

        raw_stary = history.deleted[0] if history.deleted else None
        raw_novy = history.added[0]

        # A) Spracovanie pre ENUM / TEXT -> ZurnalStavy
        if typ_dat == 'enum':
            stara_val = getattr(raw_stary, 'name', raw_stary)
            nova_val = getattr(raw_novy, 'name', raw_novy)

            if stara_val != nova_val:
                session.add(TargetModel(
                    id_zakazky=id_zakazky,
                    id_polozky=id_polozky,
                    id_zamestnanca=user_id,
                    atribut=enum_attr,
                    stara_hodnota=stara_val,
                    nova_hodnota=nova_val
                ))

        # B) Spracovanie pre DECIMAL / NUMERICKÉ -> ZurnalCeny
        elif typ_dat == 'decimal':
            def to_dec(v):
                if v is None or v == '': 
                    return None
                try: 
                    return Decimal(str(v))
                except Exception: 
                    return None

            stara_val = to_dec(raw_stary)
            nova_val = to_dec(raw_novy)

            if stara_val != nova_val:
                session.add(TargetModel(
                    id_polozky=target.id,
                    id_zamestnanca=user_id,
                    atribut=enum_attr,
                    stara_hodnota=stara_val,
                    nova_hodnota=nova_val
                ))

# Registrácia události (spúšťa sa pred uložením úpravy položky)
event.listen(Zakazka, 'before_update', zurnal_text_event)    
event.listen(Zakazka, 'after_insert', zurnal_text_event)    
event.listen(Polozka, 'before_update', zurnal_text_event)    
event.listen(Polozka, 'after_insert', zurnal_text_event)    

#autoincrement pre cislo vydavkoveho dokladu
@event.listens_for(Pokladna, 'before_insert')
def autoincrement_cislo_dokladu(mapper, connection, target):
    # Počítadlo spúšťame len ak ide o výdaj v hotovosti a číslo ešte nebolo zadané
    if target.pohyb == TypPohybu.VYDAJ and target.cislo_dokladu is None:
        
        # Zistíme najvyššie aktuálne číslo dokladu
        max_num = connection.scalar(
            db.select(func.max(Pokladna.cislo_dokladu)).where(Pokladna.pohyb == TypPohybu.VYDAJ)
        )
        
        # Ak je databáza prázdna, začínamy od 1, inak pridáme 1
        target.cislo_dokladu = (max_num or 0) + 1

#import jazykov
def init_languages(session):
    """Predvyplní databázu ISO kódmi a názvami európskych jazykov + JP a KR."""
    jazyky_data = [
        # Európske jazyky
        ('SK', 'Slovenčina'), ('CS', 'Čeština'), ('EN', 'Angličtina'), ('DE', 'Nemčina'),
        ('HU', 'Maďarčina'), ('PL', 'Poľština'), ('FR', 'Francúzština'), ('ES', 'Španielčina'),
        ('IT', 'Taliančina'), ('RU', 'Ruština'), ('UK', 'Ukrajinčina'), ('NL', 'Holandčina'),
        ('PT', 'Portugalčina'), ('RO', 'Rumunčina'), ('BG', 'Bulharčina'), ('HR', 'Chorvátčina'),
        ('SR', 'Srbčina'), ('SL', 'Slovinčina'), ('EL', 'Gréčtina'), ('DA', 'Dánčina'),
        ('SV', 'Švédčina'), ('FI', 'Fínčina'), ('NO', 'Nórčina'), ('ET', 'Estónčina'),
        ('LV', 'Lotyština'), ('LT', 'Litovčina'), ('GA', 'Írčina'), ('MT', 'Maltčina'),
        # Ázia
        ('JA', 'Japončina'), ('KO', 'Kórejčina'), ('ZH', 'Čínština')
    ]

    for kod, nazov in jazyky_data:
        existuje = session.query(Jazyk).filter_by(kod=kod).first()
        if not existuje:
            session.add(Jazyk(kod=kod, nazov=nazov))
    session.commit()                        
