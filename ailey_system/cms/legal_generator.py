"""
Ailey CMS — Legal Page Generator
==================================
EU-konforme Impressum und Datenschutz-Seiten auf Knopfdruck.
Templates nach deutschem Recht (TMG §5, DSGVO Art.13/14).
"""

import time


def generate_impressum(config: dict) -> str:
    """Generate a German-standard Impressum page (TMG §5)."""
    template = config.get("template", "de-standard")

    company = config.get("companyName", "")
    address = config.get("address", "")
    phone = config.get("phone", "")
    email = config.get("email", "")
    ceo = config.get("ceo", "")
    registration = config.get("registration", "")
    vat_id = config.get("vatId", "")
    ust_id = config.get("ustId", vat_id)
    chamber = config.get("chamberOfCommerce", "")
    profession = config.get("profession", "")
    supervisory = config.get("supervisory", "")

    sections = []

    sections.append(f"""<h1>Impressum</h1>

<h2>Angaben gemäß § 5 TMG</h2>
<p>
{company}<br>
{address}
</p>""")

    if ceo:
        label = "Geschäftsführer" if template == "de-standard" else "Vertreten durch"
        if template == "de-verein":
            label = "Vorstand"
        sections.append(f"""<h2>{label}</h2>
<p>{ceo}</p>""")

    phone_line = f"Telefon: {phone}<br>" if phone else ""
    sections.append(f"""<h2>Kontakt</h2>
<p>
{phone_line}
E-Mail: {email}
</p>""")

    if registration:
        sections.append(f"""<h2>Registereintrag</h2>
<p>{registration}</p>""")

    if ust_id:
        sections.append(f"""<h2>Umsatzsteuer-ID</h2>
<p>Umsatzsteuer-Identifikationsnummer gemäß § 27a Umsatzsteuergesetz:<br>
{ust_id}</p>""")

    if chamber:
        sections.append(f"""<h2>Kammerzugehörigkeit</h2>
<p>{chamber}</p>""")

    if profession and template == "de-freiberufler":
        supervisory_line = f"Zuständige Aufsichtsbehörde: {supervisory}" if supervisory else ""
        sections.append(f"""<h2>Berufsbezeichnung und berufsrechtliche Regelungen</h2>
<p>Berufsbezeichnung: {profession}<br>
{supervisory_line}
</p>""")

    # EU ODR
    sections.append("""<h2>EU-Streitschlichtung</h2>
<p>Die Europäische Kommission stellt eine Plattform zur Online-Streitbeilegung (OS) bereit:
<a href="https://ec.europa.eu/consumers/odr/" target="_blank" rel="noopener">https://ec.europa.eu/consumers/odr/</a>.</p>
<p>Unsere E-Mail-Adresse finden Sie oben im Impressum.</p>

<h2>Verbraucherstreitbeilegung / Universalschlichtungsstelle</h2>
<p>Wir sind nicht bereit oder verpflichtet, an Streitbeilegungsverfahren vor einer
Verbraucherschlichtungsstelle teilzunehmen.</p>""")

    return "\n\n".join(sections)


def generate_datenschutz(config: dict, impressum_config: dict = None) -> str:
    """Generate a German DSGVO-standard Datenschutzerklärung."""
    template = config.get("template", "de-dsgvo-standard")
    contact_email = config.get("contactEmail", "")
    analytics = config.get("analytics", "none")
    cookies = config.get("cookies", "essential-only")
    services = config.get("externalServices", [])

    company = ""
    address = ""
    if impressum_config:
        company = impressum_config.get("companyName", "")
        address = impressum_config.get("address", "")
        if not contact_email:
            contact_email = impressum_config.get("email", "")

    sections = []

    # Header
    responsible_hint = ('Dessen Kontaktdaten können Sie dem Abschnitt '
                        '„Hinweis zur Verantwortlichen Stelle" in dieser '
                        'Datenschutzerklärung entnehmen.') if company else ''
    sections.append(f"""<h1>Datenschutzerklärung</h1>

<h2>1. Datenschutz auf einen Blick</h2>
<h3>Allgemeine Hinweise</h3>
<p>Die folgenden Hinweise geben einen einfachen Überblick darüber, was mit Ihren
personenbezogenen Daten passiert, wenn Sie diese Website besuchen. Personenbezogene Daten
sind alle Daten, mit denen Sie persönlich identifiziert werden können. Ausführliche
Informationen zum Thema Datenschutz entnehmen Sie unserer unter diesem Text aufgeführten
Datenschutzerklärung.</p>

<h3>Datenerfassung auf dieser Website</h3>
<p><strong>Wer ist verantwortlich für die Datenerfassung auf dieser Website?</strong></p>
<p>Die Datenverarbeitung auf dieser Website erfolgt durch den Websitebetreiber.
{responsible_hint}</p>

<p><strong>Wie erfassen wir Ihre Daten?</strong></p>
<p>Ihre Daten werden zum einen dadurch erhoben, dass Sie uns diese mitteilen. Hierbei kann
es sich z.B. um Daten handeln, die Sie in ein Kontaktformular eingeben.</p>
<p>Andere Daten werden automatisch oder nach Ihrer Einwilligung beim Besuch der Website
durch unsere IT-Systeme erfasst. Das sind vor allem technische Daten (z.B. Internetbrowser,
Betriebssystem oder Uhrzeit des Seitenaufrufs). Die Erfassung dieser Daten erfolgt
automatisch, sobald Sie diese Website betreten.</p>""")

    # Responsible party
    if company:
        sections.append(f"""<h2>2. Hinweis zur verantwortlichen Stelle</h2>
<p>Die verantwortliche Stelle für die Datenverarbeitung auf dieser Website ist:</p>
<p>
{company}<br>
{address}<br>
E-Mail: {contact_email}
</p>
<p>Verantwortliche Stelle ist die natürliche oder juristische Person, die allein oder
gemeinsam mit anderen über die Zwecke und Mittel der Verarbeitung von personenbezogenen
Daten (z.B. Namen, E-Mail-Adressen o. Ä.) entscheidet.</p>""")

    # Hosting
    sections.append("""<h2>3. Hosting</h2>
<p>Die Inhalte unserer Website werden bei einem externen Hosting-Anbieter gehostet.
Die personenbezogenen Daten, die auf dieser Website erfasst werden, werden auf den
Servern des Hosters gespeichert. Hierbei kann es sich v.a. um IP-Adressen,
Kontaktanfragen, Meta- und Kommunikationsdaten, Vertragsdaten, Kontaktdaten,
Namen, Websitezugriffe und sonstige Daten, die über eine Website generiert werden,
handeln.</p>
<p>Der Einsatz des Hosters erfolgt im Interesse einer sicheren, schnellen und
effizienten Bereitstellung unseres Online-Angebots durch einen professionellen
Anbieter (Art. 6 Abs. 1 lit. f DSGVO).</p>""")

    # SSL
    sections.append("""<h2>4. SSL- bzw. TLS-Verschlüsselung</h2>
<p>Diese Seite nutzt aus Sicherheitsgründen und zum Schutz der Übertragung
vertraulicher Inhalte eine SSL- bzw. TLS-Verschlüsselung. Eine verschlüsselte
Verbindung erkennen Sie daran, dass die Adresszeile des Browsers von „http://"
auf „https://" wechselt und an dem Schloss-Symbol in Ihrer Browserzeile.</p>""")

    # Server logs
    sections.append("""<h2>5. Server-Log-Dateien</h2>
<p>Der Provider der Seiten erhebt und speichert automatisch Informationen in
so genannten Server-Log-Dateien, die Ihr Browser automatisch an uns übermittelt.
Dies sind:</p>
<ul>
<li>Browsertyp und Browserversion</li>
<li>verwendetes Betriebssystem</li>
<li>Referrer URL</li>
<li>Hostname des zugreifenden Rechners</li>
<li>Uhrzeit der Serveranfrage</li>
<li>IP-Adresse</li>
</ul>
<p>Eine Zusammenführung dieser Daten mit anderen Datenquellen wird nicht
vorgenommen.</p>
<p>Die Erfassung dieser Daten erfolgt auf Grundlage von Art. 6 Abs. 1 lit. f
DSGVO. Der Websitebetreiber hat ein berechtigtes Interesse an der technisch
fehlerfreien Darstellung und der Optimierung seiner Website.</p>""")

    # Contact form
    sections.append("""<h2>6. Kontaktformular</h2>
<p>Wenn Sie uns per Kontaktformular Anfragen zukommen lassen, werden Ihre
Angaben aus dem Anfrageformular inklusive der von Ihnen dort angegebenen
Kontaktdaten zwecks Bearbeitung der Anfrage und für den Fall von Anschlussfragen
bei uns gespeichert. Diese Daten geben wir nicht ohne Ihre Einwilligung weiter.</p>
<p>Die Verarbeitung dieser Daten erfolgt auf Grundlage von Art. 6 Abs. 1 lit. b
DSGVO, sofern Ihre Anfrage mit der Erfüllung eines Vertrags zusammenhängt oder
zur Durchführung vorvertraglicher Maßnahmen erforderlich ist. In allen übrigen
Fällen beruht die Verarbeitung auf unserem berechtigten Interesse an der
effektiven Bearbeitung der an uns gerichteten Anfragen (Art. 6 Abs. 1 lit. f
DSGVO).</p>""")

    # Cookies
    section_num = 7
    if cookies != "none":
        cookie_text = """<h2>7. Cookies</h2>
<p>Unsere Internetseiten verwenden so genannte „Cookies". Cookies sind kleine
Datenpakete und richten auf Ihrem Endgerät keinen Schaden an. Sie werden
entweder vorübergehend für die Dauer einer Sitzung (Session-Cookies) oder
dauerhaft (permanente Cookies) auf Ihrem Endgerät gespeichert.</p>"""

        if cookies == "essential-only":
            cookie_text += """<p>Diese Website verwendet ausschließlich technisch notwendige Cookies,
die für den Betrieb der Seite erforderlich sind. Technisch notwendige
Cookies werden auf Grundlage von Art. 6 Abs. 1 lit. f DSGVO gespeichert.</p>"""
        else:
            cookie_text += """<p>Neben technisch notwendigen Cookies können auch Analyse- und
Marketing-Cookies zum Einsatz kommen. Hierfür holen wir vorab Ihre
Einwilligung ein (Art. 6 Abs. 1 lit. a DSGVO). Sie können diese
Einwilligung jederzeit widerrufen.</p>"""

        sections.append(cookie_text)
        section_num = 8

    # Google Fonts
    if "google-fonts" in services:
        sections.append(f"""<h2>{section_num}. Google Fonts (lokales Hosting)</h2>
<p>Diese Seite nutzt zur einheitlichen Darstellung von Schriftarten so genannte
Google Fonts. Die Google Fonts sind lokal installiert. Eine Verbindung zu Servern
von Google findet dabei nicht statt.</p>
<p>Weitere Informationen zu Google Fonts finden Sie unter
<a href="https://developers.google.com/fonts/faq" target="_blank" rel="noopener">
https://developers.google.com/fonts/faq</a>.</p>""")
        section_num += 1

    # YouTube
    if "youtube" in services:
        sections.append(f"""<h2>{section_num}. YouTube (Erweiterter Datenschutzmodus)</h2>
<p>Diese Website bindet Videos der Website YouTube ein. Betreiber der Website
ist die Google Ireland Limited („Google"), Gordon House, Barrow Street,
Dublin 4, Irland.</p>
<p>Wir nutzen YouTube im erweiterten Datenschutzmodus. Dieser Modus bewirkt
laut YouTube, dass YouTube keine Informationen über die Besucher auf dieser
Website speichert, bevor diese sich das Video ansehen.</p>
<p>Die Nutzung von YouTube erfolgt im Interesse einer ansprechenden Darstellung
unserer Online-Angebote. Dies stellt ein berechtigtes Interesse im Sinne von
Art. 6 Abs. 1 lit. f DSGVO dar.</p>""")
        section_num += 1

    # Analytics
    if analytics and analytics != "none":
        if "matomo" in analytics.lower():
            sections.append(f"""<h2>{section_num}. Matomo</h2>
<p>Diese Website benutzt den Open-Source-Webanalysedienst Matomo.</p>
<p>Matomo verwendet Technologien, die die seitenübergreifende Wiedererkennung
des Nutzers zur Analyse des Nutzerverhaltens ermöglichen. Die durch die Matomo
erfassten Informationen über die Benutzung dieser Website werden auf unserem
Server gespeichert. Die IP-Adresse wird vor der Speicherung anonymisiert.</p>
<p>Die Nutzung dieses Analyse-Tools erfolgt auf Grundlage von Art. 6 Abs. 1
lit. f DSGVO.</p>""")
            section_num += 1

    # Rights
    sections.append(f"""<h2>{section_num}. Ihre Rechte</h2>
<p>Sie haben jederzeit das Recht, unentgeltlich Auskunft über Herkunft,
Empfänger und Zweck Ihrer gespeicherten personenbezogenen Daten zu erhalten.
Sie haben außerdem ein Recht, die Berichtigung oder Löschung dieser Daten zu
verlangen. Wenn Sie eine Einwilligung zur Datenverarbeitung erteilt haben,
können Sie diese Einwilligung jederzeit für die Zukunft widerrufen. Außerdem
haben Sie das Recht, unter bestimmten Umständen die Einschränkung der
Verarbeitung Ihrer personenbezogenen Daten zu verlangen.</p>
<p>Des Weiteren steht Ihnen ein Beschwerderecht bei der zuständigen
Aufsichtsbehörde zu.</p>
<p>Hierzu sowie zu weiteren Fragen zum Thema Datenschutz können Sie sich
jederzeit an uns wenden: <a href="mailto:{contact_email}">{contact_email}</a></p>""")

    return "\n\n".join(sections)


def generate_legal_pages(site: dict) -> dict:
    """Generate both Impressum and Datenschutz for a site.
    Returns dict with 'impressum_html' and 'datenschutz_html'.
    """
    legal = site.get("legal", {})
    imp_config = legal.get("impressum", {})
    ds_config = legal.get("datenschutz", {})

    return {
        "impressum_html": generate_impressum(imp_config),
        "datenschutz_html": generate_datenschutz(ds_config, imp_config),
    }
