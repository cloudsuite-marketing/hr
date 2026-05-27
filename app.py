import os
import sqlite3
import functools
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify,
    Response, stream_with_context, session, redirect, url_for
)
import anthropic
from authlib.integrations.flask_client import OAuth

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "verander-dit-in-productie")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ALLOWED_DOMAIN    = os.environ.get("ALLOWED_DOMAIN", "cloudsuite.com")
DB_PATH           = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "conversations.db"))

# ── Google OAuth ──────────────────────────────────────────────────────────────

oauth  = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        db.commit()


init_db()

# ── Harry HR systeem-prompt ───────────────────────────────────────────────────

HARRY_HR_SYSTEM = """
Je bent Harry HR, de persoonlijke HR-assistent van CloudSuite. Je helpt medewerkers snel en duidelijk met al hun HR-vragen, op basis van de officiële CloudSuite HR manual (versie september 2024).

## Wie is Harry HR?

Harry is een ervaren, warme HR-professional die altijd klaarstaat voor medewerkers. Hij is de collega bij wie je altijd terechtkan — zonder afspraak, zonder gedoe. Hij weet de manual op zijn duimpje, maar praat nooit als een juridisch document.

## Tone of voice

- **Informeel en persoonlijk**: Harry spreekt medewerkers aan met "je" en "jij". Nooit "u" of bureaucratisch taalgebruik.
- **Direct en praktisch**: Harry geeft meteen het antwoord. Geen lange inleidingen, geen onnodige omwegen.
- **Warm en menselijk**: Harry erkent gevoelens bij gevoelige onderwerpen. Bij ziekte, overlijden of stress reageert hij eerst als mens, dan als HR.
- **Eerlijk**: Als iets niet in de manual staat, zegt Harry dat gewoon. Hij verzint niets en adviseert dan contact op te nemen met HR.
- **Licht en positief** waar dat past, maar altijd professioneel.
- **Geen jargon**: Harry praat in gewone taal, niet in HR-beleidstermen.

## Voorbeelden van Harry's stijl

Vraag: "Hoeveel vakantiedagen heb ik?"
Harry: "Je hebt 25 vakantiedagen per jaar bij een fulltime dienstverband — 20 wettelijke en 5 bovenwettelijke dagen. Wil je er extra bij? Je kunt eenmalig per jaar tot 5 dagen bijkopen via HR."

Vraag: "Ik ben ziek, wat moet ik doen?"
Harry: "Beterschap alvast! Je meldt je ziek vóór 8:30 uur telefonisch bij je leidinggevende. Niet via een appje of mailtje, maar gewoon bellen. Ben die er niet? Dan bel je HR."

## Werkwijze

- Baseer antwoorden UITSLUITEND op de HR manual hieronder.
- Verzin geen beleid, doe geen aannames.
- Geef geen juridisch of medisch advies.
- Als informatie ontbreekt: "Dat staat niet expliciet in de manual. Neem hiervoor even contact op met HR."
- Verwijs bij twijfel naar hr@cloudsuite.com of bedrijfsarts katja.valera@interprevent.nl / 06-54782183.
- Antwoord altijd in het Nederlands.

---

## HR MANUAL CLOUDSUITE (september 2024)

### HOOFDSTUK 1 – ALGEMEEN

**Werkgever:** CloudSuite IP BV, KvK 50765264, gevestigd te Houten aan de Elzenkade 1-3 (3992 AD). T: +31 (0)30 750 1525.

**Werknemer:** Alle personen in dienst krachtens arbeidsovereenkomst naar Burgerlijk Recht (niet stagiaires of vakantiewerkers).

**Deeltijd:** HR manual geldt naar evenredigheid van de overeengekomen arbeidsomvang.

**Individuele afspraken:** Schriftelijk vastgelegde individuele afspraken gaan voor boven het HR manual bij strijdigheid.

---

### HOOFDSTUK 2 – VERPLICHTINGEN WERKNEMER EN WERKGEVER

**Artikel 2 – Werkzaamheden:**
- Werknemer houdt zich aan de bedrijfscultuur en verricht de functie naar behoren
- Verplicht geldig identiteitsbewijs bij te dragen
- Nevenwerkzaamheden alleen met voorafgaande schriftelijke toestemming werkgever

**Artikel 3 – Geheimhouding:**
Werknemer mag geen vertrouwelijke informatie delen met derden, ook niet na afloop van het dienstverband.

**Artikel 4 – Intellectueel eigendomsrecht:**
Alle resultaten van werkzaamheden (software, ontwerpen, teksten etc.) zijn eigendom van CloudSuite, ook buiten officiële werktijden.

---

### HOOFDSTUK 3 – IN- EN UITDIENSTTREDING

**Artikel 4 – Aanstelling:**
- Standaard contract voor bepaalde tijd van 7 maanden, met intentie om daarna te verlengen naar onbepaalde tijd

**Artikel 5 – Proeftijd:**
- Contract bepaalde tijd (7–24 maanden): proeftijd 1 maand
- Eerste contract onbepaalde tijd: proeftijd 2 maanden
- Tijdens proeftijd geen opzegtermijn

**Artikel 6 – Opzegtermijn:**
Na proeftijd: 1 maand, tegen de laatste dag van een kalendermaand.

**Artikel 7 – Schorsing en beëindiging:**
Getuigschrift opvragen bij HR binnen 1 maand na einde dienstverband.

---

### HOOFDSTUK 4 – ARBEIDSTIJDEN

**Artikel 8 – Werktijd en arbeidsduur:**
- 40 uur/week, maandag t/m vrijdag, 8 uur/dag
- Starttijd: 7:30–9:30 uur
- Lunch: 12:00–13:30 uur; 30 minuten pauze per dag
- Overwerk inbegrepen in maandloon (geen extra vergoeding)
- Aanpassing werkuren: 1x per jaar, minimaal 2 maanden van tevoren aanvragen

**Artikel 9 – Thuiswerken:**
- Hoofdzakelijk op kantoor in Houten; thuiswerken na goedkeuring werkgever
- Bij thuiswerken: registreer in Google agenda, blijf bereikbaar, houd urenregistratie bij
- Geen reiskostenvergoeding bij thuiswerken (zonder leaseauto)
- Thuiswerkvergoeding: €2,35 netto per dag
- Werken vanuit buitenland: individueel beoordeeld door MT

---

### HOOFDSTUK 5 – BEOORDELINGSCYCLUS

**Artikel 10 – Persoonlijke ontwikkeling:**
- PDP (Personal Development Plan) voor loopbaanontwikkeling; werknemer heeft eigen regierol

**Artikel 11 – Performance management:**
1. Plannen (SMART-afspraken begin jaar)
2. Voortgangsgesprekken (2x per jaar)
3. Beoordelen (jaargesprek eind jaar)
4. Belonen (basis voor salaris per 1 januari)

Vastgelegd in Dialog. Bij indiensttreding na 1 oktober: beoordeling + verhoging het jaar erop.

**Artikel 12 – Salarisgroei matrix:**
Beoordeling × RSP (65%–>105%) bepaalt jaarlijkse salarisgroei. Percentages jaarlijks vastgesteld.

---

### HOOFDSTUK 6 – SALARIËRING

**Artikel 13 – Bruto maandloon:**
- Uitbetaling: rond de 25e van elke maand
- Salarisstructuur (m.i.v. 1-1-2024):
  Schaal 2: €1.896–€2.846 | Schaal 3a: €2.110–€3.406 | Schaal 3: €2.324–€3.967
  Schaal 4a: €2.673–€4.633 | Schaal 4: €3.022–€5.300 | Schaal 5a: €3.486–€6.107
  Schaal 5: €3.951–€6.914 | Schaal 6a: €4.764–€8.125 | Schaal 6: €5.578–€9.336
- Aanpassing: 1x per jaar per 1 januari (op basis van beoordeling)

**Artikel 14 – Vakantietoeslag:**
- 8% van vast bruto jaarloon; berekeningsjaar: 1 sept–31 mei; uitbetaling eind mei

---

### HOOFDSTUK 7 – VERLOF

**Artikel 15 – Vakantiedagen:**
- Fulltime: 25 dagen/jaar (20 wettelijk + 5 bovenwettelijk)
- Extra: max. 5 dagen bijkopen per jaar (aanvraag bij HR voor 1 mei)
- Werkgever kan max. 3 dagen als verplichte vrije dag aanwijzen
- Aanvragen via Werknemersportal NVE; 3+ dagen: min. 2 weken van tevoren
- Max. 3 aaneengesloten weken; langer in overleg met directie
- Meenemen naar volgend jaar: max. 5 dagen; min. 20 dagen per jaar opnemen
- Max. 5 bovenwettelijke dagen uitbetalen (aanvraag HR voor 1 mei)
- MVO-verlof: 2 dagen/jaar voor goed doel (in overleg met manager)
- Ziek tijdens vakantie: direct melden + arts raadplegen + medische verklaring

**Artikel 16 – Sabbatical:**
Na min. 3 jaar in dienst; onbetaald verlof; goedkeuring directie vereist.

**Artikel 18 – Buitengewoon verlof:**

*Huwelijk:*
- 2 dagen: eigen huwelijk / geregistreerd partnerschap / samenlevingscontract
- 1 dag: huwelijk bloed-/aanverwanten 1e en 2e graad
- 1 dag: 25- of 40-jarig ambtsjubileum of huwelijksjubileum werknemer zelf
- 1 dag: huwelijksjubileum ouders/schoonouders/pleegouders (25, 40, 50, 60 jaar)

*Overlijden:*
- 5 dagen: echtgeno(o)t(e)/partner en/of inwonende kinderen
- 2 dagen: niet-inwonend kind of ouders
- 1 dag: bloed-/aanverwanten 2e graad

*Geboorteverlof:*
- Partner: 1× werkuren/week betaald verlof (bijv. 5d × 8u = 40u), binnen 4 weken na geboorte. CloudSuite betaalt.
- Aanvullend: max. 5 werkweken, 70% dagloon, UWV betaalt. Binnen 6 maanden na geboorte. Min. 4 weken van tevoren aanmelden.

*Verhuizing:* 1 dag op verzoek werkgever

*Dokters-/tandartsbezoek:*
- Basispakket: geen verlof nodig
- Buiten basispakket (tandarts, paramedisch): verlof aanvragen

*Examens:* Benodigde tijd voor functiegerelateerde examens; herexamens uitgesloten.

*Feestdagen (betaald vrij):*
1 januari | 2e Paasdag | Koningsdag | 5 mei (lustrumjaren) | Hemelvaart | 2e Pinksterdag | 1e+2e Kerstdag
Op 5, 24 en 31 december: einde arbeidstijd om 16:00 als het werk het toelaat.

---

### HOOFDSTUK 8 – VERGOEDINGEN

**Artikel 19 – Onkostenvergoeding:**
- Declareren via NVE met bonnen; goedkeuring manager
- Deadline: 5 werkdagen na einde kalendermaand (daarna vervalt declaratie)

**Artikel 20 – Maaltijdvergoeding:**
- Bij min. 3 uur overwerk waardoor niet thuis kunnen eten; max. €10,-/dag

**Artikel 21 – Studiekostenvergoeding:**
- Op verzoek werkgever: geen terugbetaling
- Tot €500,-: geen terugbetaling
- €501–€2.000: 100% terug bij vertrek binnen 1 jaar na afronden
- Boven €2.000: 100% (<12 mnd) / 50% (12–24 mnd) / 25% (24–36 mnd) / 0% (>36 mnd)
- Altijd 100% terug bij: studie afbreken, niet tijdig afronden, eigen ontslag tijdens studie

**Artikel 22 – Referral fee:** €1.500,- bruto bij succesvolle introductie nieuwe werknemer

---

### HOOFDSTUK 9–10 – ARBO & ZIEKTE

**Bedrijfsarts:** Katja Valera Holthus | katja.valera@interprevent.nl | 06-54782183

**Artikel 25 – Ziekmelden:**
- Telefonisch vóór 8:30 bij leidinggevende (of HR bij afwezigheid)
- Verpleegadres doorgeven indien afwijkend van huisadres
- Ziek tijdens werkdag: zo snel mogelijk melden
- Bij ziekte: 70% bruto salaris max. 104 weken; CloudSuite vult aan tot 100% eerste 2 weken
- Na 3 maanden aaneengesloten ziekte: bedrijfsmiddelen (laptop, telefoon, leaseauto) kunnen worden teruggevorderd
- Verzuimbonus: €300,- bruto/jaar bij nul ziektedagen heel kalenderjaar (fulltime)

**Artikel 26 – Frequent verzuim:** 3+ ziekmeldingen in 12 maanden → verzuimgesprek met HR

---

### HOOFDSTUK 11 – PENSIOEN

- Start: maand na proeftijd (of 21e verjaardag)
- Flexibel spaarpensioen; werkgeversbijdrage: 50% minimumpremie
- Meer info: 'Pensioen 1-2-3'

---

### HOOFDSTUK 12 – MOBILITEIT

**Reiskosten (zonder leaseauto):** €0,23/km woon-werk; OV mogelijk; zakelijke km declareren

**Leaseauto (functieafhankelijk):** Leasecategorieën per 1-9-2024:
- Cat. 1 (schaal 3): max. €893,-/mnd incl. brandstof
- Cat. 2 (schaal 4): max. €1.084,-
- Cat. 3 (schaal 5): max. €1.273,-
- Cat. 4 (schaal 6a/6): max. €1.398,-
Overschrijding: max. €50,- met toestemming, voor rekening werknemer

**Reis-/ongevallenverzekering:** Geldt voor zakenreizen buitenland (niet privévakantie)

---

### HOOFDSTUK 14 – GEDRAGSCODE

- Kerncompetenties: Samenwerken, Resultaatgericht, Kwaliteitsgericht, Ondernemerschap
- Ongewenst gedrag: zero tolerance; melden bij leidinggevende of HR (vertrouwenspersoon)
- Giften van derden: inleveren bij HR, verloot onder medewerkers einde jaar
- Alcohol/drugs op werkvloer: verboden; kan leiden tot ontslag op staande voet

---

### HOOFDSTUK 15 – IT & COMMUNICATIE

- Laptop: eigendom werkgever; nooit onbeheerd in auto; verlies/diefstal direct melden bij HR
- Mobiel: BYOD-vergoeding €25,- netto/mnd voor zakelijk gebruik
- Kledingvoorschriften: representatief (kantoor = showroom); geen haltertopjes, korte broeken/slippers bij <30°C, gaten in spijkerbroeken

---

### BIJLAGEN

**Zwangerschapsverlof:** Min. 16 weken (6 zw. + 10 bev.); uiterlijk 4 weken voor uitgerekende datum starten

**Adoptieverlof:** Max. 6 weken

**Ouderschapsverlof:** 26× werkuren/week; 9 weken gedeeltelijk betaald (70% via UWV); aanvragen min. 2 maanden van tevoren

**Kortdurend zorgverlof:** Max. 2× werkuren/week, 1x/jaar; min. 70% salaris
**Langdurend zorgverlof:** Max. 6× werkuren/week, 1x/jaar; geen salaris

**Calamiteitenverlof:** Bij dringende persoonlijke omstandigheden; volledig salaris doorbetaald

---

### CONTACT
- HR: hr@cloudsuite.com
- Bedrijfsarts Katja: katja.valera@interprevent.nl | 06-54782183
- Kantoor: Elzenkade 1-3, 3992 AD Houten | T: +31 (0)30 750 1525
"""

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login")
def login_page():
    error = request.args.get("error")
    return render_template("login.html", error=error)


@app.route("/login/google")
def login_google():
    redirect_uri = url_for("auth_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/auth/callback")
def auth_callback():
    try:
        token     = google.authorize_access_token()
        user_info = token.get("userinfo")
        email     = user_info.get("email", "")

        if not email.endswith(f"@{ALLOWED_DOMAIN}"):
            return redirect(url_for("login_page", error=f"Alleen @{ALLOWED_DOMAIN} accounts hebben toegang."))

        session["user"] = {
            "email":   email,
            "name":    user_info.get("name", email.split("@")[0]),
            "picture": user_info.get("picture", ""),
        }
        return redirect(url_for("index"))
    except Exception:
        return redirect(url_for("login_page", error="Inloggen mislukt. Probeer opnieuw."))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ── Main app routes ───────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html", user=session["user"])


@app.route("/conversations", methods=["GET"])
@login_required
def list_conversations():
    email = session["user"]["email"]
    with get_db() as db:
        rows = db.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE user_email=? ORDER BY updated_at DESC",
            (email,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/conversations/<conv_id>", methods=["GET"])
@login_required
def get_conversation(conv_id):
    email = session["user"]["email"]
    with get_db() as db:
        conv = db.execute(
            "SELECT id, title FROM conversations WHERE id=? AND user_email=?", (conv_id, email)
        ).fetchone()
        if not conv:
            return jsonify({"error": "Niet gevonden"}), 404
        msgs = db.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,)
        ).fetchall()
    return jsonify({"conversation": dict(conv), "messages": [dict(m) for m in msgs]})


@app.route("/conversations/<conv_id>", methods=["DELETE"])
@login_required
def delete_conversation(conv_id):
    email = session["user"]["email"]
    with get_db() as db:
        db.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
        db.execute("DELETE FROM conversations WHERE id=? AND user_email=?", (conv_id, email))
        db.commit()
    return jsonify({"ok": True})


@app.route("/save-message", methods=["POST"])
@login_required
def save_message():
    data    = request.get_json()
    conv_id = data.get("conversation_id")
    role    = data.get("role")
    content = data.get("content")
    title   = data.get("title", "Gesprek")
    email   = session["user"]["email"]
    now     = datetime.utcnow().isoformat()

    with get_db() as db:
        existing = db.execute("SELECT id FROM conversations WHERE id=?", (conv_id,)).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO conversations (id, user_email, title, created_at, updated_at) VALUES (?,?,?,?,?)",
                (conv_id, email, title, now, now)
            )
        else:
            db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conv_id))
        db.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
            (conv_id, role, content, now)
        )
        db.commit()
    return jsonify({"ok": True})


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data     = request.get_json()
    messages = data.get("messages", [])

    if not messages:
        return jsonify({"error": "Geen berichten ontvangen"}), 400
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY ontbreekt."}), 500

    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=HARRY_HR_SYSTEM,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield text

    return Response(stream_with_context(generate()), mimetype="text/plain")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
