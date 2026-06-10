# -*- coding: utf-8 -*-
"""
IHK Mediengestalter Digital & Print — Prüfungsthemen 2026

Echte Prüfungsthemen mit jeweils 20 hardcoded Fragen + 3 Musterantworten.
Bereich: "Medien konzipieren, gestalten und präsentieren" (Alle Fachrichtungen)

Themen:
  U1: Corporate Design Beratung
  U2: Zielgruppenanalyse
  U3: Logo-Entwurf
  U4: Webseiten-Gestaltung
  U5: Flyer-Gestaltung
  U6: Schutzrechte
  U7: Korrekturen durchführen
  U8: Protokolle

Frage-Typen:
  "mc"    — Multiple Choice (4 Optionen, 1 korrekt)
  "open"  — Offene Frage mit 3 Musterantworten (LLM-bewertet)
  "tf"    — True/False
"""

from typing import Dict, List


# ──────────────────────────────────────────────────────────────
# HELPER
# ──────────────────────────────────────────────────────────────

def _mc(question: str, options: list, correct: int, explanation: str = "", topic: str = "") -> Dict:
    return {
        "type": "mc", "question": question,
        "options": options, "correct": correct,
        "explanation": explanation, "topic": topic,
    }

def _tf(question: str, correct: bool, explanation: str = "", topic: str = "") -> Dict:
    return {
        "type": "tf", "question": question,
        "correct": correct, "explanation": explanation,
        "topic": topic,
    }

def _open(question: str, model_answers: List[str], key_points: List[str] = None,
          topic: str = "") -> Dict:
    """Open-ended question with model answers for LLM comparison scoring."""
    return {
        "type": "open", "question": question,
        "model_answers": model_answers,
        "key_points": key_points or [],
        "topic": topic,
    }


# ══════════════════════════════════════════════════════════════
# U1: CORPORATE DESIGN BERATUNG
# ══════════════════════════════════════════════════════════════

U1_THEORY = (
    "**Corporate Design Beratung**\n\n"
    "Corporate Design ist der visuelle Teil der Corporate Identity – also wie ein Unternehmen "
    "nach außen hin aussieht. Es sorgt dafür, dass ein Unternehmen auf allen Medien einheitlich "
    "und wiedererkennbar wirkt.\n\n"
    "**Bestandteile eines Corporate Designs:**\n"
    "- Logo (Farbe, SW, Negativ)\n"
    "- Hausfarben (CMYK, RGB, HEX, Pantone)\n"
    "- Hausschriften (Schriftfamilien, Einsatzbereiche)\n"
    "- Bildsprache (Stil der Fotos, Illustrationen, Icons)\n"
    "- Gestaltungsraster\n"
    "- CD-Handbuch / Styleguide\n\n"
    "**CD-Beratungsprozess:**\n"
    "1. Ist-Analyse — Was hat der Kunde bereits?\n"
    "2. Briefing — Werte, Zielgruppe, Wettbewerb\n"
    "3. Entwurf & Präsentation — Varianten zeigen\n"
    "4. Argumentation — Wiedererkennungswert, Vertrauen\n"
    "5. Styleguide-Erstellung — Alle Regeln dokumentieren"
)

U1_QUIZ: List[Dict] = [
    _open(
        "Was versteht man unter Corporate Design?",
        [
            "Corporate Design ist der visuelle Teil der Corporate Identity. Es umfasst alle gestalterischen Elemente, die ein Unternehmen nach außen einheitlich darstellen, wie Logo, Farben und Schriften.",
            "Corporate Design bezeichnet das einheitliche Erscheinungsbild eines Unternehmens. Es sorgt dafür, dass alle Medien – von der Visitenkarte bis zur Website – wiedererkennbar und konsistent gestaltet sind.",
            "Unter Corporate Design versteht man das visuelle Regelwerk eines Unternehmens. Es definiert, wie das Unternehmen auf allen Kommunikationsmitteln visuell aufzutreten hat, um einen hohen Wiedererkennungswert zu erzielen.",
        ],
        key_points=["visueller Teil", "Corporate Identity", "einheitlich", "Wiedererkennungswert", "Logo", "Farben", "Schriften"],
        topic="Corporate Design Grundlagen",
    ),
    _mc(
        "Welche Bestandteile gehören zu einem vollständigen Corporate Design?",
        ["Logo, Hausfarben, Hausschriften, Bildsprache, Styleguide",
         "Nur Logo und Visitenkarte",
         "Website, Social Media, Newsletter",
         "Nur die Unternehmensfarben"],
        0,
        "Ein vollständiges CD umfasst Logo, Farben, Schriften, Bildsprache und einen Styleguide.",
        topic="Corporate Design Bestandteile",
    ),
    _open(
        "Was ist ein Styleguide und warum ist er wichtig?",
        [
            "Ein Styleguide ist ein Dokument, das alle Regeln des Corporate Designs festlegt. Er ist wichtig, damit alle Mitarbeiter und externen Dienstleister das CD korrekt und einheitlich anwenden.",
            "Der Styleguide ist das Regelwerk des Corporate Designs. Er beschreibt genau, wie Logo, Farben und Schriften eingesetzt werden dürfen, und verhindert, dass das CD falsch verwendet wird.",
            "Ein Styleguide dokumentiert verbindlich alle gestalterischen Vorgaben eines Unternehmens. Er ist wichtig, weil ohne ihn jeder Gestalter das CD anders interpretieren würde, was zu einem uneinheitlichen Erscheinungsbild führt.",
        ],
        key_points=["Regelwerk", "einheitlich", "Logo", "Farben", "Schriften", "verbindlich"],
        topic="Styleguide",
    ),
    _open(
        "Wie gehen Sie vor, wenn ein Kunde sein bestehendes Corporate Design überarbeiten möchte?",
        [
            "Zunächst führe ich eine Ist-Analyse durch und schaue, welche Elemente bereits vorhanden sind und wo Inkonsistenzen bestehen. Dann bespreche ich mit dem Kunden, was beibehalten und was erneuert werden soll.",
            "Ich beginne mit einem ausführlichen Briefing-Gespräch, um die Ziele der Überarbeitung zu verstehen. Danach analysiere ich das bestehende CD, erarbeite Verbesserungsvorschläge und präsentiere diese dem Kunden.",
            "Der Prozess startet mit einer Bestandsaufnahme aller vorhandenen Materialien. Anschließend wird gemeinsam mit dem Kunden definiert, was das neue CD ausdrücken soll, bevor Entwürfe entwickelt und präsentiert werden.",
        ],
        key_points=["Ist-Analyse", "Briefing", "Bestandsaufnahme", "Entwürfe", "Präsentation"],
        topic="CD-Überarbeitung",
    ),
    _mc(
        "Was ist der Unterschied zwischen Corporate Identity und Corporate Design?",
        ["CI umfasst Design, Kommunikation und Verhalten – CD ist nur der visuelle Teil",
         "Es gibt keinen Unterschied",
         "CD ist das Gesamtkonzept, CI nur das Logo",
         "CI ist für Print, CD für Digital"],
        0,
        "Corporate Identity ist das Gesamtbild (Design + Communication + Behavior), Corporate Design nur der visuelle Anteil.",
        topic="CI vs. CD",
    ),
    _open(
        "Warum ist ein einheitliches Corporate Design für ein Unternehmen wichtig?",
        [
            "Ein einheitliches CD schafft Wiedererkennungswert und Vertrauen bei den Kunden. Es vermittelt Professionalität und macht das Unternehmen auf allen Kanälen sofort erkennbar.",
            "Einheitlichkeit im CD stärkt die Marke und macht sie unverwechselbar. Kunden verbinden das Erscheinungsbild mit bestimmten Werten, was Vertrauen und Loyalität fördert.",
            "Ein konsistentes Corporate Design differenziert das Unternehmen vom Wettbewerb. Es sorgt dafür, dass alle Kommunikationsmittel aus einem Guss wirken und die Unternehmensidentität klar transportieren.",
        ],
        key_points=["Wiedererkennungswert", "Vertrauen", "Professionalität", "einheitlich", "Marke"],
        topic="Bedeutung CD",
    ),
    _open(
        "Was sind Hausfarben und wie werden sie definiert?",
        [
            "Hausfarben sind die festgelegten Farben eines Unternehmens, die auf allen Medien verwendet werden. Sie werden mit exakten Werten in CMYK für den Druck, RGB und HEX für digitale Medien sowie Pantone für Sonderfarben definiert.",
            "Hausfarben sind die offiziellen Unternehmensfarben, die im CD festgelegt sind. Durch die Angabe aller Farbwerte – CMYK, RGB, HEX, Pantone – wird sichergestellt, dass die Farben auf allen Medien möglichst identisch erscheinen.",
            "Unter Hausfarben versteht man die verbindlich definierten Farben eines Unternehmens. Sie werden in verschiedenen Farbsystemen angegeben, um eine konsistente Darstellung sowohl in Druckerzeugnissen als auch auf digitalen Medien zu gewährleisten.",
        ],
        key_points=["CMYK", "RGB", "HEX", "Pantone", "einheitlich", "Farbwerte"],
        topic="Hausfarben",
    ),
    _open(
        "Was versteht man unter dem Schutzraum eines Logos?",
        [
            "Der Schutzraum ist ein definierter Mindestabstand rund um das Logo, in dem keine anderen Elemente platziert werden dürfen. Er sorgt dafür, dass das Logo immer klar und ungestört wirkt.",
            "Der Schutzraum ist eine Freifläche um das Logo herum, die im Styleguide festgelegt ist. Er schützt das Logo vor visueller Überfrachtung und stellt sicher, dass es immer gut lesbar bleibt.",
            "Unter Schutzraum versteht man den Mindestabstand, den das Logo zu anderen Gestaltungselementen haben muss. Er wird oft anhand eines Buchstabens oder eines Teils des Logos definiert und im CD-Handbuch verbindlich festgelegt.",
        ],
        key_points=["Mindestabstand", "Freifläche", "Styleguide", "Logo", "keine anderen Elemente"],
        topic="Logo-Schutzraum",
    ),
    _open(
        "Wie präsentieren Sie einem Kunden ein neues Corporate Design?",
        [
            "Ich präsentiere das CD mit konkreten Anwendungsbeispielen wie Visitenkarte, Briefbogen und Website-Mockup. So kann der Kunde sehen, wie das CD in der Praxis wirkt.",
            "Zunächst erkläre ich das Konzept hinter dem Entwurf und welche Werte er transportiert. Dann zeige ich verschiedene Varianten und Anwendungsbeispiele.",
            "Eine gute Präsentation zeigt das CD in realistischen Szenarien – auf Werbemitteln, digitalen Medien und Printprodukten. Ich erkläre die gestalterischen Entscheidungen und beziehe den Kunden aktiv ein.",
        ],
        key_points=["Anwendungsbeispiele", "Mockups", "Varianten", "Konzept erklären"],
        topic="CD-Präsentation",
    ),
    _mc(
        "Was sind typische Fehler bei der CD-Anwendung?",
        ["Falsche Farbwerte, unautorisierte Logoänderungen, fremde Schriften",
         "Zu viel Einheitlichkeit",
         "Zu genaues Befolgen des Styleguides",
         "Verwendung von Vektorgrafiken"],
        0,
        "Typische Fehler: Logo verzerrt, falsche Farben, nicht genehmigte Schriften.",
        topic="CD-Fehler",
    ),
    _open(
        "Was ist eine Bildsprache im Kontext des Corporate Designs?",
        [
            "Die Bildsprache definiert, welchen visuellen Stil Fotos und Illustrationen im CD haben sollen – z. B. ob Bilder eher warm oder kühl, gestellt oder authentisch sein sollen.",
            "Bildsprache beschreibt die gestalterische Linie, der alle verwendeten Bilder folgen sollen. Sie umfasst Motivwahl, Bildstil, Farbanmutung und Bildkomposition.",
            "Die Bildsprache legt fest, wie Bilder im Unternehmen eingesetzt werden, um eine einheitliche visuelle Wirkung zu erzielen.",
        ],
        key_points=["Bildstil", "Fotos", "Illustrationen", "einheitlich", "Farbanmutung"],
        topic="Bildsprache",
    ),
    _mc(
        "Welche Logoformate sollten im CD-Paket enthalten sein?",
        ["Vektor (AI, EPS, SVG) + PNG mit Transparenz, in Farbe, SW und Negativ",
         "Nur JPEG in Farbe",
         "Nur PDF",
         "Nur das Originalformat aus Illustrator"],
        0,
        "Ein vollständiges Logopaket enthält Vektor- und Pixelformate in allen Varianten.",
        topic="Logoformate",
    ),
    _open(
        "Was ist der Unterschied zwischen primären und sekundären Hausfarben?",
        [
            "Primäre Hausfarben sind die Hauptfarben des Unternehmens, die auf allen Medien dominieren. Sekundäre Farben ergänzen die Primärfarben und werden für Akzente oder Infografiken genutzt.",
            "Primärfarben sind die zentralen Unternehmensfarben, die sofort mit der Marke assoziiert werden. Sekundärfarben bieten gestalterische Flexibilität.",
            "Die Primärfarbe ist die Hauptfarbe, die das Unternehmen repräsentiert. Sekundärfarben sind ergänzende Farben für eine größere gestalterische Bandbreite.",
        ],
        key_points=["Hauptfarbe", "ergänzend", "Akzente", "Marke", "Flexibilität"],
        topic="Primär/Sekundärfarben",
    ),
    _open(
        "Warum sollten Hausschriften für verschiedene Einsatzbereiche definiert werden?",
        [
            "Weil eine Schrift, die im Druck gut aussieht, auf einer Website schwer lesbar sein kann. Im Styleguide wird festgelegt, welche Schrift für Headlines, Fließtext und digitale Medien verwendet wird.",
            "Verschiedene Einsatzbereiche stellen unterschiedliche Anforderungen. So braucht man für Web eine Webfont-Lizenz, während für Druck die Desktop-Lizenz ausreicht.",
            "Schriften wirken je nach Medium unterschiedlich. Durch festgelegte Schriften für Überschriften, Fließtext und Sonderfälle bleibt das CD einheitlich.",
        ],
        key_points=["Lesbarkeit", "Web vs. Print", "Lizenz", "einheitlich", "Einsatzbereiche"],
        topic="Hausschriften",
    ),
    _mc(
        "Wie erkennt man, ob ein bestehendes Corporate Design veraltet ist?",
        ["Es wirkt nicht mehr zeitgemäß, funktioniert digital schlecht, passt nicht zur Positionierung",
         "Wenn es älter als 1 Jahr ist",
         "Wenn der Chef es nicht mehr mag",
         "Wenn die Konkurrenz das gleiche CD hat"],
        0,
        "Veraltetes CD: inkonsistenter Einsatz, schlechte digitale Varianten, passt nicht mehr zur Marke.",
        topic="CD-Modernisierung",
    ),
    _tf(
        "CD-konform bedeutet, dass alle Vorgaben des Styleguides eingehalten werden.",
        True,
        "CD-konform = korrekte Farben, Schriften, Logo-Version, Abstände wie im Styleguide definiert.",
        topic="CD-Konformität",
    ),
    _open(
        "Wie können KI-Tools im CD-Prozess eingesetzt werden?",
        [
            "KI kann bei der Ideenfindung für Farbpaletten und Gestaltungskonzepte unterstützen. Auch die automatische Anpassung von Layouts auf verschiedene Formate kann durch KI beschleunigt werden.",
            "KI-Tools können Bildmaterial generieren, das zur Bildsprache des CDs passt, oder automatisch prüfen, ob ein Entwurf alle CD-Vorgaben einhält.",
            "Im CD-Prozess kann KI für die schnelle Generierung von Entwurfsvarianten genutzt werden. Wichtig ist aber, dass ein Mensch die finale Entscheidung trifft.",
        ],
        key_points=["Ideenfindung", "Automatisierung", "Layout-Anpassung", "menschliche Kontrolle"],
        topic="KI im CD-Prozess",
    ),
    _open(
        "Was ist ein Moodboard und wozu dient es im CD-Prozess?",
        [
            "Ein Moodboard ist eine visuelle Sammlung von Bildern, Farben, Schriften und Texturen, die die Stimmung und Richtung des geplanten CDs zeigt.",
            "Ein Moodboard visualisiert die kreative Richtung vor der eigentlichen Gestaltung. Es zeigt dem Kunden, welche Anmutung das CD haben soll.",
            "Moodboards dienen als Kommunikationsmittel zwischen Gestalter und Kunde. Sie helfen dabei, ein gemeinsames Verständnis für Stil, Farbe und Aussage zu entwickeln.",
        ],
        key_points=["Stimmung", "Richtung", "Kommunikation", "Bilder", "Farben", "Schriften"],
        topic="Moodboard",
    ),
    _open(
        "Was passiert, wenn kein Styleguide vorhanden ist?",
        [
            "Ohne Styleguide interpretiert jeder Gestalter das CD anders. Es entstehen Inkonsistenzen, was den Wiedererkennungswert der Marke schwächt.",
            "Ohne klare Vorgaben wird das CD uneinheitlich umgesetzt. Mitarbeiter und externe Dienstleister arbeiten nach eigenem Ermessen.",
            "Das Fehlen eines Styleguides führt langfristig zur Verwässerung der Marke. Verschiedene Farbwerte, falsche Schriften schaden dem Markenauftritt.",
        ],
        key_points=["Inkonsistenz", "uneinheitlich", "Wiedererkennungswert", "Verwässerung"],
        topic="Fehlender Styleguide",
    ),
    _open(
        "Welche Fragen stellen Sie in einem Briefing-Gespräch zum Corporate Design?",
        [
            "Ich frage nach den Unternehmenswerten, der Zielgruppe, dem Wettbewerbsumfeld und dem bisherigen Erscheinungsbild. Außerdem kläre ich, welche Medien bespielt werden und welches Budget zur Verfügung steht.",
            "Wichtige Fragen: Was macht das Unternehmen einzigartig? Wie soll es wahrgenommen werden? Welche Farben oder Stile werden bevorzugt oder abgelehnt?",
            "Im Briefing frage ich nach Zielgruppe, Unternehmensphilosophie, Wettbewerbern und den geplanten Kommunikationskanälen.",
        ],
        key_points=["Unternehmenswerte", "Zielgruppe", "Wettbewerb", "Medien", "Budget"],
        topic="CD-Briefing",
    ),
]


# ══════════════════════════════════════════════════════════════
# U2: ZIELGRUPPENANALYSE
# ══════════════════════════════════════════════════════════════

U2_THEORY = (
    "**Zielgruppenanalyse**\n\n"
    "Die Zielgruppenanalyse ermittelt, für wen ein Medium produziert wird – um Gestaltung, "
    "Sprache und Kanal optimal anzupassen.\n\n"
    "**Merkmale zur Beschreibung einer Zielgruppe:**\n"
    "- Demografisch: Alter, Geschlecht, Wohnort, Bildung, Einkommen\n"
    "- Psychografisch: Werte, Interessen, Lebensstil, Einstellungen\n"
    "- Verhaltensbezogen: Kaufverhalten, Mediennutzung, Markentreue\n\n"
    "**Methoden:**\n"
    "- Personas — fiktive, realistische Nutzerprofile\n"
    "- Sinus-Milieus — gesellschaftliche Gruppen nach Werten und Lebensstil\n"
    "- Umfragen & Interviews — direkte Befragung\n"
    "- Marktforschungsdaten — Sekundärquellen\n\n"
    "**Einfluss auf Gestaltung:**\n"
    "- Jüngere Zielgruppe → moderne Schriften, kräftige Farben, Social Media\n"
    "- Ältere Zielgruppe → größere Schrift, ruhigeres Layout\n"
    "- B2B → sachlich, professionell\n"
    "- B2C → emotional, erlebnisorientiert"
)

U2_QUIZ: List[Dict] = [
    _open("Was versteht man unter einer Zielgruppenanalyse?",
        ["Eine Zielgruppenanalyse ist die systematische Untersuchung der Menschen, die mit einem Medium angesprochen werden sollen.",
         "Die Zielgruppenanalyse ermittelt, wer die Empfänger einer Kommunikationsmaßnahme sind. Nur wenn man die Zielgruppe kennt, kann man Gestaltung, Sprache und Medium optimal ausrichten.",
         "Unter Zielgruppenanalyse versteht man die Erfassung und Auswertung aller relevanten Merkmale der angestrebten Empfängergruppe."],
        key_points=["systematisch", "Empfänger", "Merkmale", "Gestaltung anpassen"], topic="ZG-Grundlagen"),
    _mc("Welche demografischen Merkmale sind relevant?",
        ["Alter, Geschlecht, Bildung, Einkommen", "Nur das Alter", "Nur der Wohnort", "Hobby und Lieblingsfarbe"],
        0, "Demografisch: Alter, Geschlecht, Wohnort, Bildung, Einkommen.", topic="Demografische Merkmale"),
    _open("Was sind psychografische Merkmale und warum sind sie wichtig?",
        ["Psychografische Merkmale beschreiben Werte, Interessen, Lebensstil und Einstellungen. Sie erklären, warum Menschen so handeln wie sie handeln.",
         "Sie gehen über reine Fakten hinaus und beschreiben die innere Welt der Zielgruppe – Meinungen, Hobbys, Werte.",
         "Psychografische Merkmale sind Charaktereigenschaften und Lebensstilaspekte. Zwei Menschen gleichen Alters können völlig unterschiedliche Wünsche haben."],
        key_points=["Werte", "Interessen", "Lebensstil", "Motivation"], topic="Psychografische Merkmale"),
    _open("Was ist eine Persona und wie wird sie erstellt?",
        ["Eine Persona ist ein fiktives, aber realistisches Nutzerprofil mit Name, Alter, Beruf, Zielen und Problemen.",
         "Eine Persona fasst Zielgruppen-Eigenschaften in einer konkreten Musterperson zusammen, basierend auf Recherchen und Daten.",
         "Personas werden erstellt, indem man typische Merkmale zu einer fiktiven Person verdichtet – mit Name, Gesicht und Geschichte."],
        key_points=["fiktiv", "realistisch", "Name", "Beruf", "Ziele", "Daten"], topic="Personas"),
    _open("Was sind die Sinus-Milieus?",
        ["Die Sinus-Milieus teilen die Gesellschaft in Gruppen mit ähnlichen Werten und Lebensstilen ein.",
         "Sie unterteilen die Bevölkerung nach Wertvorstellungen und sozialer Lage in verschiedene Lebenswelten.",
         "Das Modell gruppiert Menschen nach gemeinsamen Grundwerten und Alltagseinstellungen, nicht nur nach Einkommen."],
        key_points=["Werte", "Lebensstil", "soziale Lage", "Lebenswelten"], topic="Sinus-Milieus"),
    _mc("Wie beeinflusst die Zielgruppe die Wahl des Mediums?",
        ["Jüngere über Social Media, Ältere über Print/TV – Mediennutzung bestimmt den Kanal",
         "Gar nicht – das Medium wählt man nach Budget",
         "Alle Zielgruppen nutzen die gleichen Medien",
         "Das Medium bestimmt die Zielgruppe, nicht umgekehrt"],
        0, "Die Mediennutzung der Zielgruppe bestimmt, wo die Botschaft platziert wird.", topic="Medienwahl"),
    _open("Wie beeinflusst die Zielgruppe die Gestaltung eines Mediums?",
        ["Junge Zielgruppe: dynamisch, kräftige Farben, kurze Texte. Ältere: ruhiges Layout, größere Schrift.",
         "Die Gestaltung muss die Sprache der Zielgruppe sprechen – für Kinder bunt, für Unternehmer sachlich.",
         "Zielgruppenmerkmale beeinflussen Farbe, Typografie, Bildsprache und Tonalität eines Mediums."],
        key_points=["Farbe", "Schrift", "Bildsprache", "Tonalität", "anpassen"], topic="ZG und Gestaltung"),
    _mc("Was ist der Unterschied zwischen B2B und B2C?",
        ["B2B: sachlich, informativ, professionell — B2C: emotional, erlebnisorientiert",
         "Kein Unterschied",
         "B2B ist günstiger",
         "B2C ist nur für Print"],
        0, "B2B = Business to Business (sachlich), B2C = Business to Consumer (emotional).", topic="B2B vs. B2C"),
    _open("Warum ist die Zielgruppenanalyse vor der Gestaltung so wichtig?",
        ["Ohne Kenntnis der Zielgruppe gestaltet man am Nutzer vorbei.",
         "Sie verhindert Fehlinvestitionen, da man sonst Budget für Medien ausgibt, die niemand sieht.",
         "Sie bildet die Grundlage jeder erfolgreichen Kommunikationsmaßnahme."],
        key_points=["am Nutzer vorbei", "Fehlinvestition", "Grundlage"], topic="Bedeutung ZGA"),
    _mc("Welche Methoden gibt es zur Erhebung von Zielgruppendaten?",
        ["Umfragen, Interviews, Fokusgruppen, Web-Analytics, Sekundärquellen",
         "Nur Google Analytics",
         "Nur persönliche Interviews",
         "Man fragt den Chef"],
        0, "Primär: Umfragen, Interviews. Sekundär: Analytics, Studien, Statistiken.", topic="Erhebungsmethoden"),
    _open("Was ist eine Zielgruppensegmentierung?",
        ["Die Aufteilung einer großen Zielgruppe in kleinere, homogenere Untergruppen.",
         "Segmentierung unterteilt eine heterogene Gesamtgruppe nach gemeinsamen Merkmalen.",
         "Segmentierung ermöglicht präzisere Kommunikation für jedes Segment."],
        key_points=["Aufteilung", "homogen", "präzise", "Segmente"], topic="Segmentierung"),
    _open("Wie verändert sich die Gestaltung eines Flyers je nach Zielgruppe?",
        ["Für Jugendliche: moderne Schriften, kräftige Farben. Für Senioren: größere Schrift, mehr Weißraum.",
         "Bildwahl, Sprache und Layout variieren. Streetart-Elemente für Jugendliche, seriöse Bilder für Senioren.",
         "Farbwelt, Bildsprache, Schriftgröße und Textmenge variieren je nach Zielgruppe."],
        key_points=["Schrift", "Farben", "Weißraum", "Bildsprache", "anpassen"], topic="ZG-abhängige Gestaltung"),
    _open("Was versteht man unter Zielgruppenaffinität?",
        ["Wie gut ein Medium zur Zielgruppe passt. Hohe Affinität = Zielgruppe nutzt das Medium überproportional häufig.",
         "Affinität beschreibt, wie stark eine Gruppe mit einem Medium in Berührung kommt.",
         "Je höher die Affinität, desto passender ist das Medium für die Zielgruppenansprache."],
        key_points=["Affinität", "Medium passt", "überproportional"], topic="Zielgruppenaffinität"),
    _open("Wie hilft eine Zielgruppenanalyse bei der Wahl der Farben?",
        ["Jüngere, kreative Zielgruppen reagieren auf lebendige Farben, konservative auf gedecktere Töne.",
         "Farben transportieren Botschaften und wecken Emotionen – die Analyse zeigt, welche Farbwelten ankommen.",
         "Die Analyse hilft zu verstehen, welche emotionalen Bedeutungen Farben für die Gruppe haben."],
        key_points=["Emotion", "Farbwelten", "Zielgruppe", "kulturell"], topic="Farbwahl"),
    _mc("Was sind typische Fehler bei der Zielgruppenanalyse?",
        ["Eigene Meinung statt Daten, zu breite Zielgruppe, veraltete Daten",
         "Zu viele Personas erstellen",
         "Zu genaue Analyse",
         "Zu viel Geld für Umfragen ausgeben"],
        0, "Häufige Fehler: Annahmen statt Daten, zu breit definiert, veraltete Infos.", topic="ZGA-Fehler"),
    _open("Wie unterscheidet sich Kommunikation für Kinder von der für Erwachsene?",
        ["Kinder: einfache Sprache, große Schriften, bunte Bilder. Erwachsene: komplexere Inhalte, kleinere Schrift.",
         "Für Kinder: visuell, spielerisch, bildunterstützt. Für Erwachsene: mehr Text, feinere Typografie.",
         "Kinder brauchen einfache Botschaften und positive Emotionen. Erwachsene verstehen Ironie und differenzierte Argumente."],
        key_points=["einfach", "visuell", "spielerisch", "komplex", "Lesbarkeit"], topic="Kinder vs. Erwachsene"),
    _mc("Was ist der Unterschied zwischen Primär- und Sekundärzielgruppe?",
        ["Primär = Hauptzielgruppe, Sekundär = beeinflusst Kaufentscheidung indirekt",
         "Primär = jung, Sekundär = alt",
         "Es gibt keinen Unterschied",
         "Primär = online, Sekundär = offline"],
        0, "Primärzielgruppe = direkt angesprochen. Sekundärzielgruppe = Einfluss auf Entscheidung (z.B. Eltern).", topic="Primär/Sekundär-ZG"),
    _open("Wie beeinflusst die Zielgruppe die Textmenge auf einem Medium?",
        ["Wenig Zeit/Leseaffinität → kurze Texte. Fachpublikum → detaillierte Informationen.",
         "Viel Text überfordert bestimmte Zielgruppen. Andere erwarten ausführliche Inhalte.",
         "Die Textmenge richtet sich nach Erwartungen und Gewohnheiten der Zielgruppe."],
        key_points=["Leseaffinität", "kurz vs. detailliert", "Gewohnheiten"], topic="Textmenge"),
    _open("Wie kann man prüfen, ob eine Gestaltung zur Zielgruppe passt?",
        ["Durch Nutzertests mit echten Vertretern der Zielgruppe.",
         "A/B-Tests bieten die Möglichkeit, Varianten zu testen und die bessere zu messen.",
         "Fokusgruppen, Klickraten, Verweildauer und Konversionen zeigen, ob die Gestaltung wirkt."],
        key_points=["Nutzertests", "A/B-Tests", "Fokusgruppen", "Feedback"], topic="Gestaltungs-Check"),
    _mc("Welche Rolle spielt die Mediennutzung in der Zielgruppenanalyse?",
        ["Sie zeigt welche Kanäle die Zielgruppe nutzt und wo Budget hingehört",
         "Keine Rolle",
         "Nur für TV-Werbung relevant",
         "Mediennutzung kann man nicht messen"],
        0, "Mediennutzung bestimmt den Kanal – ohne diese Info riskiert man, die ZG nicht zu erreichen.", topic="Mediennutzung"),
]


# ══════════════════════════════════════════════════════════════
# U3–U8: WEITERE THEMEN (kompakt, key facts + Mix aus mc/open)
# ══════════════════════════════════════════════════════════════

U3_THEORY = (
    "**Logo-Entwurf**\n\n"
    "**Kriterien für ein gutes Logo:** Einprägsam, einfach, zeitlos, vielseitig, passend.\n\n"
    "**Logo-Typen:** Wortmarke (Google), Bildmarke (Apple), Kombinationsmarke, Wort-Bild-Marke.\n\n"
    "**Entwurfsprozess:** Briefing → Skizzen → Digitalisierung → Varianten → Präsentation.\n\n"
    "**Technisch:** Immer als Vektor (SVG, AI, EPS). Farben exakt definiert. Schutzraum festlegen.\n"
    "Varianten: Farbe, SW, Negativ. Verschiedene Größen testen."
)

U3_QUIZ: List[Dict] = [
    _mc("Welche Kriterien muss ein gutes Logo erfüllen?",
        ["Einprägsam, einfach, vielseitig, zeitlos, passend", "Möglichst bunt und komplex",
         "Nur wiedererkennbar", "Muss in 3D funktionieren"], 0, topic="Logo-Kriterien"),
    _open("Was ist der Unterschied zwischen Wort- und Bildmarke?",
        ["Wortmarke = nur Schrift (Google). Bildmarke = nur Symbol (Apple).",
         "Wortmarke nutzt den Namen als Element. Bildmarke ist ein Symbol, das ohne Text funktioniert.",
         "Wortmarken sind textbasiert, Bildmarken sind ikonische Symbole."],
        key_points=["Schrift", "Symbol", "Text", "Bild"], topic="Logo-Typen"),
    _mc("Warum muss ein Logo als Vektorgrafik vorliegen?",
        ["Verlustfrei skalierbar für alle Größen", "Weil JPEGs nicht drucken können",
         "Vektoren sind billiger", "Das ist nur eine Empfehlung"], 0, topic="Vektor"),
    _open("Was ist eine Negativversion eines Logos?",
        ["Logo in umgekehrten Farben – weiß auf dunklem Hintergrund.",
         "Dreht die Farbgebung um für dunkle Hintergründe.",
         "Sorgt dafür, dass das Logo auf allen Hintergründen erkennbar bleibt."],
        key_points=["umgekehrte Farben", "dunkler Hintergrund", "erkennbar"], topic="Negativversion"),
    _open("Beschreiben Sie den Entwurfsprozess eines Logos.",
        ["Briefing → Recherche → Skizzen → Digitalisierung → Varianten → Präsentation.",
         "Briefing analysieren, Handskizzen erstellen, beste Ideen digitalisieren, präsentieren.",
         "Briefing → Analyse → Handskizzen → Vektorisierung → Varianten → Feedback → Finalisierung."],
        key_points=["Briefing", "Skizzen", "Digitalisierung", "Varianten", "Präsentation"], topic="Logo-Prozess"),
    _mc("Warum sollte man beim Logo-Entwurf mit Handskizzen beginnen?",
        ["Schnell viele Ideen entwickeln, bevor man sich digital festlegt",
         "Weil Computer verboten sind", "Handskizzen sind günstiger", "Pflicht laut DIN-Norm"], 0, topic="Handskizzen"),
    _open("Was ist der Unterschied zwischen Logo-Refresh und Rebranding?",
        ["Refresh: behutsame Modernisierung, Wiedererkennungswert bleibt. Rebranding: vollständige Neugestaltung.",
         "Refresh = Evolution, kleine Anpassungen. Rebranding = Revolution, altes Logo komplett verworfen.",
         "Refresh behält die Kernidentität. Rebranding verändert die Marke grundlegend."],
        key_points=["Refresh", "Modernisierung", "Rebranding", "neu", "Wiedererkennungswert"], topic="Refresh vs. Rebranding"),
    _mc("Was ist ein Favicon?",
        ["Kleines Icon im Browser-Tab, vereinfachte Logo-Version", "Ein Animationsformat",
         "Ein Druckformat", "Ein Social-Media-Filter"], 0, topic="Favicon"),
    _open("Wie schützt man ein Logo rechtlich?",
        ["Markenanmeldung beim DPMA. Eingetragene Marke schützt vor Nachahmung.",
         "Eintragung beim DPMA gibt exklusives Nutzungsrecht für bestimmte Klassen.",
         "Urheberrecht entsteht automatisch, aber Markenanmeldung gibt aktives, durchsetzbares Recht."],
        key_points=["DPMA", "Markenanmeldung", "Schutz", "Nutzungsrecht"], topic="Logo-Schutz"),
    _open("Kann KI beim Logo-Entwurf eingesetzt werden?",
        ["KI kann in der Inspirationsphase nützlich sein. Professionelles Logo braucht aber menschliche Arbeit.",
         "KI-Tools können schnell Varianten generieren. Ergebnis muss kritisch bewertet werden.",
         "KI kann unterstützen, aber finale Logoentwicklung erfordert menschliches Urteilsvermögen."],
        key_points=["Inspiration", "Varianten", "menschliche Kontrolle", "Qualität"], topic="KI und Logo"),
    _mc("Was ist der Unterschied zwischen einem Logo und einem Icon?",
        ["Logo = offizielles Markenzeichen. Icon = universelles Symbol für Funktionen",
         "Kein Unterschied", "Icons sind größer", "Logos sind nur für Print"], 0, topic="Logo vs. Icon"),
    # Ergänzende Fragen
    _tf("Ein Logo muss auch in Schwarzweiß funktionieren.", True,
        "Der SW-Test prüft, ob die Form allein ausreichend stark ist.", topic="SW-Test"),
    _mc("Welche Farbwirkung hat Blau?",
        ["Vertrauenswürdig und seriös", "Aggressiv und laut", "Verspielt und kindlich", "Traurig"], 0, topic="Farbwirkung"),
    _open("Was versteht man unter Skalierbarkeit eines Logos?",
        ["Das Logo muss in jeder Größe – vom Briefkopf bis zur Plakatwand – klar erkennbar sein.",
         "Ein skalierbares Logo funktioniert als Vektor in allen Größen ohne Qualitätsverlust.",
         "Skalierbarkeit ist eine Grundvoraussetzung: erkennbar auf dem Kugelschreiber wie auf dem Banner."],
        key_points=["jede Größe", "Vektor", "verlustfrei", "erkennbar"], topic="Skalierbarkeit"),
    _mc("Was ist eine Kombinationsmarke?",
        ["Logo aus Schrift + Symbol, die auch getrennt einsetzbar sind",
         "Zwei Logos übereinandergelegt", "Ein animiertes Logo", "Nur Text in zwei Farben"], 0, topic="Kombinationsmarke"),
    _open("Welche Schriftaspekte sind beim Logo zu beachten?",
        ["Schrift muss zur Unternehmensidentität passen und auch klein lesbar sein.",
         "Qualitativ hochwertige, lizenzierte Schriften verwenden.",
         "Schrift muss zeitlos sein, in verschiedenen Auflösungen gut aussehen."],
        key_points=["passend", "lesbar", "lizenziert", "zeitlos"], topic="Logo-Typografie"),
    _tf("Ein Logo sollte möglichst viele Details enthalten, damit es einprägsam ist.", False,
        "Ein gutes Logo ist einfach und klar – weniger ist mehr.", topic="Logo-Einfachheit"),
    _mc("Was bedeutet 'Schutzraum' bei einem Logo?",
        ["Mindestabstand um das Logo, in dem keine anderen Elemente stehen dürfen",
         "Der Copyright-Schutz", "Ein physischer Raum im Büro", "Die Verpackung"], 0, topic="Schutzraum"),
    _open("Warum sind Logodesign-Trends mit Vorsicht zu genießen?",
        ["Trends altern schnell – ein Logo soll zeitlos sein und langfristig funktionieren.",
         "Trends geben Inspiration, dürfen aber nicht die einzige Richtschnur sein.",
         "Ein trendiges Logo läuft Gefahr, in 5 Jahren veraltet zu wirken."],
        key_points=["zeitlos", "Trend", "langfristig", "veraltet"], topic="Logo-Trends"),
    _open("Wie reagieren Sie, wenn der Kunde einen Logo-Entwurf ablehnt?",
        ["Gezielt nachfragen was nicht passt (Farbe, Form, Wirkung) und neue Varianten erarbeiten.",
         "Konstruktive Kritik aufnehmen, Missverständnisse klären, Alternativen zeigen.",
         "Klären welche Aspekte nicht passen und gezielt in die gewünschte Richtung entwickeln."],
        key_points=["Feedback", "nachfragen", "Varianten", "gezielt"], topic="Kundenfeedback Logo"),
]

# ── U4: Webseiten-Gestaltung ──

U4_THEORY = (
    "**Webseiten-Gestaltung**\n\n"
    "**Grundlagen:** Grid-Systeme, RGB/HEX-Farbwahl, Web-Schriften, Responsive Design.\n\n"
    "**UX vs. UI:** UX = Wie fühlt sich die Nutzung an? UI = Wie sieht es aus?\n\n"
    "**Responsive Design:** Mobile First, Breakpoints (320px, 768px, 1200px).\n\n"
    "**Barrierefreiheit:** Kontrast mind. 4.5:1 (WCAG AA), Alt-Texte, Tastaturnavigation.\n\n"
    "**Wichtig:** Nutzerführung, Call to Action, Ladezeit optimieren, Bildformate (JPEG, PNG, SVG, WebP)."
)

U4_QUIZ: List[Dict] = [
    _open("Was versteht man unter Responsive Design?",
        ["Website passt sich automatisch an verschiedene Bildschirmgrößen an.",
         "Flexible Anpassung des Layouts für Smartphone, Tablet und Desktop.",
         "Gestaltungsansatz, bei dem die Website auf allen Endgeräten funktioniert."],
        key_points=["anpassen", "Bildschirmgröße", "Smartphone", "Desktop"], topic="Responsive Design"),
    _mc("Was bedeutet 'Mobile First'?",
        ["Zuerst für Mobile gestalten, dann für größere Bildschirme erweitern",
         "Mobile Version weglassen", "Zuerst Desktop, dann Mobile", "Nur eine App bauen"], 0, topic="Mobile First"),
    _mc("Was ist der Unterschied zwischen UX und UI?",
        ["UX = Nutzungserfahrung (intuitiv?), UI = visuelles Erscheinungsbild (Farben, Buttons)",
         "Kein Unterschied", "UX ist für Mobile, UI für Desktop", "UX = Programmierung, UI = Design"], 0, topic="UX vs. UI"),
    _mc("Was sind Breakpoints im Webdesign?",
        ["Bildschirmbreiten, ab denen sich das Layout ändert (z.B. 768px, 1200px)",
         "Fehler im Code", "Maximale Dateigröße für Bilder", "Seitenumbrüche beim Druck"], 0, topic="Breakpoints"),
    _open("Was versteht man unter Barrierefreiheit im Webdesign?",
        ["Website auch für Menschen mit Einschränkungen zugänglich: Kontrast, Alt-Texte, Tastaturnavigation.",
         "Barrierefreie Website ist für alle nutzbar, unabhängig von Einschränkungen. WCAG AA: Kontrast 4.5:1.",
         "Inhalte für jeden zugänglich: semantisches HTML, Kontrast, Screenreader-Kompatibilität."],
        key_points=["zugänglich", "Kontrast", "Alt-Texte", "WCAG", "Screenreader"], topic="Barrierefreiheit"),
    _mc("Was ist das Mindest-Kontrastverhältnis nach WCAG AA?",
        ["4.5:1", "2:1", "7:1", "10:1"], 0, "WCAG AA fordert mind. 4.5:1 für normalen Text.", topic="WCAG Kontrast"),
    _open("Was ist ein Grid-System im Webdesign?",
        ["Rastersystem mit Spalten und Abständen für konsistentes Layout.",
         "Grid gibt dem Layout unsichtbare Struktur für visuelle Ordnung.",
         "Fundament des Layouts: definiert Spalten, Abstände und Außenränder."],
        key_points=["Spalten", "Raster", "Ordnung", "konsistent"], topic="Grid-System"),
    _mc("Was ist ein Call to Action?",
        ["Aufforderung an den Nutzer zu handeln, z.B. 'Jetzt kaufen'",
         "Ein Programmierbefehl", "Eine Drucktechnik", "Ein Farbmodell"], 0, topic="CTA"),
    _open("Was ist ein Wireframe?",
        ["Schematischer Entwurf einer Website ohne gestalterische Details – zeigt Struktur und Platzierung.",
         "Skelett einer Website: wo Navigation, Inhalte, Bilder und CTAs platziert werden.",
         "Wireframes planen Struktur und Nutzerführung, bevor Zeit in visuelle Gestaltung investiert wird."],
        key_points=["Struktur", "schematisch", "ohne Design", "Planung"], topic="Wireframe"),
    _mc("Welche Bildformate eignen sich für Websites?",
        ["JPEG für Fotos, PNG für Transparenz, SVG für Vektoren, WebP für optimierte Kompression",
         "Nur JPEG", "Nur PNG", "TIFF und EPS"], 0, topic="Web-Bildformate"),
    _mc("Was ist eine Sitemap?",
        ["Strukturierte Übersicht aller Seiten einer Website", "Ein CSS-Framework",
         "Ein Farbschema", "Eine Datenbank"], 0, topic="Sitemap"),
    _open("Was versteht man unter visueller Hierarchie?",
        ["Elemente werden durch Größe, Farbe und Anordnung gewichtet – Nutzer erkennt sofort, was wichtig ist.",
         "Nutzer wird signalisiert, welche Inhalte primär, sekundär und tertiär sind.",
         "Klare Hierarchie führt den Nutzer: wichtigstes Element am größten und auffälligsten."],
        key_points=["Größe", "Farbe", "Gewichtung", "wichtig"], topic="Visuelle Hierarchie"),
    _mc("Welche Mindestschriftgröße empfiehlt sich für Fließtext auf Websites?",
        ["16px", "8px", "24px", "6pt"], 0, topic="Web-Schriftgröße"),
    _mc("Was ist der Unterschied zwischen One-Pager und klassischer Website?",
        ["One-Pager: eine Seite, Scrollen. Klassisch: mehrere verlinkte Unterseiten",
         "Kein Unterschied", "One-Pager ist teurer", "One-Pager ist immer besser"], 0, topic="One-Pager"),
    _mc("Was ist der Unterschied zwischen RGB und HEX?",
        ["Gleiche Farben, andere Notation — RGB(255,0,0) = #FF0000",
         "Komplett verschiedene Farbräume", "HEX ist für Druck", "RGB kann man nicht im Web nutzen"], 0, topic="RGB vs. HEX"),
    _open("Warum ist die Ladezeit für Webdesign relevant?",
        ["Langsame Seiten verlieren Besucher. Über 3 Sekunden → viele brechen ab. Beeinflusst auch Google-Ranking.",
         "Ladezeit ist ein Qualitätsfaktor. Bilder optimieren, Code schlank halten.",
         "Nutzer verlassen langsame Seiten. Bilder und Assets müssen fürs Web optimiert werden."],
        key_points=["Ladezeit", "3 Sekunden", "Google", "Bilder optimieren"], topic="Ladezeit"),
    _open("Was versteht man unter Nutzerführung?",
        ["Blick und Bewegung des Nutzers durch Gestaltung gezielt lenken.",
         "Intuitive Navigation durch visuelle Hierarchie und klare CTAs.",
         "Besucher ohne Nachdenken durch die Website navigieren lassen."],
        key_points=["lenken", "intuitiv", "Hierarchie", "Navigation"], topic="Nutzerführung"),
    _mc("Welches Farbmodell verwendet man im Webdesign?",
        ["RGB / HEX", "CMYK", "Pantone", "LAB"], 0, topic="Web-Farbmodell"),
    _open("Wie kann KI die Webgestaltung unterstützen?",
        ["Layoutvorschläge generieren, Bilder freistellen, Farben abstimmen, schnelle Prototypen.",
         "KI-Tools helfen bei Bildgenerierung, Platzhalterinhalten, automatischer Layout-Anpassung.",
         "KI für Prototypen, Bildoptimierung, Nutzerverhalten-Analyse. Gestalterische Entscheidungen bleiben menschlich."],
        key_points=["Layout", "Prototypen", "Bildoptimierung", "menschlich"], topic="KI im Webdesign"),
    _tf("Web-Schriften (Google Fonts) brauchen keine spezielle Lizenz.", False,
        "Auch bei Google Fonts gelten Lizenzbedingungen (SIL Open Font License). Für eigene Schriften: Web-Lizenz ≠ Desktop-Lizenz.", topic="Webfont-Lizenz"),
]


# ── U5: Flyer-Gestaltung ──

U5_THEORY = (
    "**Flyer-Gestaltung**\n\n"
    "**Format & Druck:** DIN A6/A5/DIN lang. Falzarten: Wickelfalz, Zickzackfalz, Leporello.\n"
    "Beschnittzugabe: mind. 3mm. Sicherheitsabstand: 3-5mm.\n\n"
    "**Gestaltung:** Satzspiegel, Schrifthierarchie, 300dpi für Bilder, CMYK-Farbmodus.\n\n"
    "**Druckworkflow:** Konzept → Layout in InDesign → Korrektur → PDF/X-Export → Druckerei.\n\n"
    "**Veredelung:** Glanz-/Mattlack, UV-Spotlack, Folienprägung, Stanzungen."
)

U5_QUIZ: List[Dict] = [
    _mc("Welche Beschnittzugabe ist Standard?",
        ["3mm auf jeder Seite", "1mm", "10mm", "Keine nötig"], 0, topic="Beschnittzugabe"),
    _mc("Was ist ein PDF/X?",
        ["Standardisiertes Druckformat mit eingebetteten Schriften und korrekten Farben",
         "Ein Videoformat", "Eine Webseite", "Ein RAW-Bildformat"], 0, topic="PDF/X"),
    _open("Welche Falzarten gibt es?",
        ["Wickelfalz (Seiten übereinander), Zickzackfalz (wechselseitig), Leporello, Kreuzfalz.",
         "Wickelfalz für Broschüren, Zickzackfalz für Fahrpläne/Landkarten.",
         "Einfachfalz, Wickelfalz, Zickzackfalz, Kreuzfalz – Wahl je nach Verwendungszweck."],
        key_points=["Wickelfalz", "Zickzackfalz", "Leporello", "Kreuzfalz"], topic="Falzarten"),
    _mc("Welche Mindestauflösung brauchen Bilder für Druck?",
        ["300 dpi im Endformat", "72 dpi", "150 dpi", "1000 dpi"], 0, topic="Druckauflösung"),
    _mc("Was ist ein Satzspiegel?",
        ["Der nutzbare Bereich auf einer Seite für Text und Bilder",
         "Ein Drucker", "Eine Schriftart", "Ein Farbprofil"], 0, topic="Satzspiegel"),
    _mc("Welcher Farbmodus für den Druck?",
        ["CMYK", "RGB", "HEX", "HSL"], 0, topic="CMYK"),
    _open("Was ist ein Proof?",
        ["Farbverbindlicher Kontrollausdruck vor dem Druck zur Freigabe.",
         "Simuliert das spätere Druckergebnis auf kalibriertem Ausgabegerät.",
         "Letzte Kontrolle vor dem Druck, wird vom Kunden zur Freigabe unterschrieben."],
        key_points=["farbverbindlich", "Kontrolle", "Freigabe", "kalibriert"], topic="Proof"),
    _open("Was ist Überdrucken?",
        ["Farbe wird über eine andere gedruckt statt darunter freizustellen. Schwarzer Text druckt oft überdruckend.",
         "Druckfarbe wird über bereits gedruckte Farbe gelegt. Kann gewollt oder ungewollt sein.",
         "Relevant bei schwarzem Text auf Farbhintergrund – vermeidet Passerprobleme."],
        key_points=["Farbe über Farbe", "Freistellen", "Passer", "schwarz"], topic="Überdrucken"),
    _mc("Was ist Weißraum?",
        ["Unbedruckter Bereich als Gestaltungsmittel für Übersichtlichkeit",
         "Ein Druckfehler", "Nur bei weißem Papier", "Leerer Speicherplatz"], 0, topic="Weißraum"),
    _mc("Unterschied Offset- und Digitaldruck?",
        ["Offset: hohe Auflagen, Druckplatten, gleichmäßig. Digital: kleine Auflagen, keine Platten, flexibel",
         "Kein Unterschied", "Digital ist immer besser", "Offset ist günstiger bei kleinen Auflagen"], 0, topic="Offset vs. Digital"),
    _open("Was versteht man unter Schrifthierarchie?",
        ["Verschiedene Textebenen (Headline, Subline, Fließtext) durch Größe/Gewicht klar unterscheiden.",
         "Strukturiert den Text und leitet das Auge des Lesers.",
         "Ordnet Textelemente nach Wichtigkeit – entscheidet, was zuerst wahrgenommen wird."],
        key_points=["Headline", "Fließtext", "Größe", "Gewicht", "Hierarchie"], topic="Schrifthierarchie"),
    _mc("Was ist ein Preflight?",
        ["Automatische Prüfung der Druckdatei auf Fehler vor der Übergabe",
         "Ein Flugzeug-Check", "Ein Social-Media-Tool", "Eine Schriftart"], 0, topic="Preflight"),
    _open("Wie erstellt man eine druckfertige Datei aus InDesign?",
        ["Exportieren als PDF/X, Beschnittmarken aktivieren, Schriften einbetten, CMYK-Profil.",
         "PDF/X-Standard wählen, Beschnittzugabe einstellen, Preflight prüfen.",
         "Export als PDF mit Druckerei-Preset, Beschnitt aktivieren, Farbprofil der Druckerei verwenden."],
        key_points=["PDF/X", "Beschnitt", "Schriften einbetten", "CMYK", "Preflight"], topic="Druckdaten-Export"),
    _mc("Serifenschriften vs. serifenlose Schriften?",
        ["Serifen: klassisch, elegant, führen das Auge. Sans-Serif: modern, klar, sachlich",
         "Kein visueller Unterschied", "Serifen nur für Web", "Sans-Serif nur für Druck"], 0, topic="Serifen"),
    _open("Wie beeinflusst das Papier das Erscheinungsbild?",
        ["Matt wirkt hochwertiger, glänzend lässt Farben brillanter erscheinen. Grammatur beeinflusst Qualitätseindruck.",
         "Papiersorte, Grammatur und Veredelung beeinflussen die Wirkung erheblich.",
         "Schweres Papier = Qualität. Dünnes Papier = günstig. Papierwahl muss zur Marke passen."],
        key_points=["matt", "glänzend", "Grammatur", "Qualität", "Wirkung"], topic="Papierwahl"),
    _mc("Was ist der Sicherheitsabstand?",
        ["Mindestabstand von Text/Elementen zum Rand (3-5mm) gegen Schnittungenauigkeiten",
         "Abstand zwischen zwei Druckern", "Farbabstand", "Zeilenabstand"], 0, topic="Sicherheitsabstand"),
    _open("Welche Veredelungsmöglichkeiten gibt es?",
        ["Glanz-/Mattlack, UV-Spotlack, Folienprägung, Reliefprägung, Stanzungen.",
         "Softtouch-Lack, Metallic-Folien, Blindprägung, Stanzungen für individuelle Formen.",
         "Veredelungen erhöhen Wertigkeit und Haptik – gezielt einsetzen, zur Marke passend."],
        key_points=["Lack", "UV-Spot", "Prägung", "Stanzung", "Wertigkeit"], topic="Veredelung"),
    _tf("Beim Flyerdruck muss die Beschnittzugabe über den Formatrand hinausgehen.", True,
        "Hintergründe/Farbflächen müssen über den Rand hinaus geführt werden.", topic="Beschnitt"),
    _open("Was ist eine Druckvorlage?",
        ["Fertige, druckfertige Datei mit eingebetteten Schriften, korrekten Farben und Format.",
         "Finales Dokument, das alle technischen Anforderungen der Druckerei erfüllt.",
         "Abgabebereit aufbereitete Datei – in der Regel PDF/X mit allen druckrelevanten Infos."],
        key_points=["druckfertig", "eingebettet", "PDF/X", "Format"], topic="Druckvorlage"),
    _mc("Was gehört auf einen Flyer?",
        ["Headline, Kernbotschaft, Kontaktdaten, CTA – weniger ist mehr",
         "So viel Text wie möglich", "Nur das Logo", "Mindestens 5 verschiedene Schriften"], 0, topic="Flyer-Inhalt"),
]


# ── U6: Schutzrechte ──

U6_THEORY = (
    "**Schutzrechte**\n\n"
    "**Urheberrecht:** Entsteht automatisch. Schützt Texte, Bilder, Musik, Software. 70 Jahre nach Tod.\n\n"
    "**Markenrecht:** Aktiv anmelden beim DPMA. Schützt Logos, Namen. 10 Jahre (verlängerbar).\n\n"
    "**Lizenzen:** Royalty Free (einmalig), Rights Managed (genau definiert), Creative Commons.\n\n"
    "**Schriftlizenzen:** Desktop ≠ Web ≠ App. Immer Bedingungen prüfen.\n\n"
    "**KI & Recht:** Wem gehören KI-generierte Bilder? Noch weitgehend ungeklärt."
)

U6_QUIZ: List[Dict] = [
    _mc("Wie entsteht Urheberrecht?", ["Automatisch mit der Schöpfung", "Durch Anmeldung", "Durch Bezahlung", "Durch Veröffentlichung"], 0, topic="Urheberrecht"),
    _mc("Wie lange gilt Urheberrecht?", ["70 Jahre nach Tod", "50 Jahre", "10 Jahre", "Unbegrenzt"], 0, topic="Schutzfrist"),
    _open("Unterschied Urheberrecht und Markenrecht?",
        ["Urheberrecht: automatisch, schützt kreative Werke. Markenrecht: angemeldet, schützt Namen/Logos.",
         "Urheberrecht schützt die Schöpfung automatisch. Markenrecht muss beim DPMA eingetragen werden.",
         "Urheberrecht schützt das Werk, Markenrecht die Markenidentität."],
        key_points=["automatisch", "angemeldet", "DPMA", "Werk", "Marke"], topic="UrhR vs. MarkenR"),
    _mc("Was ist das DPMA?", ["Deutsches Patent- und Markenamt", "Digital Print Marketing Agency", "Design Platform Management App", "Druckerei-Partnerschaft München-Augsburg"], 0, topic="DPMA"),
    _mc("Was ist Royalty Free?", ["Einmalige Zahlung, dann freie Nutzung (mit Einschränkungen)", "Komplett kostenlos", "Nur für Könige", "Unbegrenzte Exklusivrechte"], 0, topic="Royalty Free"),
    _open("Was sind Creative Commons Lizenzen?",
        ["Standardisiertes System, mit dem Urheber Werke mit bestimmten Nutzungsrechten teilen können.",
         "CC ermöglicht Urhebern, festzulegen wie ihr Werk genutzt werden darf – von frei bis eingeschränkt.",
         "CC-Lizenzen reichen von 'frei mit Namensnennung' bis 'keine Bearbeitung, keine kommerzielle Nutzung'."],
        key_points=["Creative Commons", "Namensnennung", "Nutzungsrechte", "Stufen"], topic="Creative Commons"),
    _mc("Was muss man bei Stockfotos beachten?", ["Lizenzbedingungen genau lesen, Verwendungszweck prüfen", "Einfach herunterladen", "Sind immer kostenlos", "Kann man beliebig bearbeiten"], 0, topic="Stockfotos"),
    _open("Was ist ein Model Release?",
        ["Schriftliche Einverständniserklärung einer abgebildeten Person zur kommerziellen Nutzung ihres Bildes.",
         "Genehmigung einer Person zur Nutzung ihres Bildes. Besonders bei Werbemotiven unverzichtbar.",
         "Ohne Model Release darf man Bilder erkennbarer Personen nicht kommerziell nutzen."],
        key_points=["Einverständnis", "Person", "kommerziell", "schriftlich"], topic="Model Release"),
    _open("Was ist das Recht am eigenen Bild?",
        ["Jede Person bestimmt selbst, ob und wie ihr Bild veröffentlicht wird. Teil des Persönlichkeitsrechts.",
         "Fotos von erkennbaren Personen dürfen nur mit deren Einwilligung veröffentlicht werden.",
         "Schützt die Persönlichkeit – auch auf öffentlichem Grund braucht man grundsätzlich Einverständnis."],
        key_points=["Persönlichkeitsrecht", "Einwilligung", "erkennbar"], topic="Recht am eigenen Bild"),
    _open("Was versteht man unter einer Schriftlizenz?",
        ["Erlaubt Nutzung einer Schrift unter bestimmten Bedingungen. Desktop ≠ Web ≠ App.",
         "Schriften sind urheberrechtlich geschützt. Für Web/App braucht man separate Lizenzen.",
         "Regelt wo und wie eine Schrift eingesetzt werden darf. Einbetten in PDFs kann extra Lizenz brauchen."],
        key_points=["Desktop", "Web", "App", "Lizenz", "urheberrechtlich"], topic="Schriftlizenz"),
    _mc("Was passiert bei Urheberrechtsverletzung?", ["Abmahnung, Unterlassung, Schadensersatz, ggf. Strafe", "Nichts", "Nur eine Verwarnung", "Man muss sich entschuldigen"], 0, topic="Urheberrechtsverletzung"),
    _open("Was ist das Zitatrecht?",
        ["Erlaubt begrenzte Nutzung fremder Werke für Auseinandersetzung/Kritik mit Quellenangabe.",
         "Unter bestimmten Bedingungen darf man zitieren – muss einen inhaltlichen Zweck erfüllen.",
         "Gesetzliche Ausnahme vom Urheberrecht für Erläuterung, Kritik oder wissenschaftliche Analyse."],
        key_points=["begrenzt", "Quelle", "Kritik", "Ausnahme"], topic="Zitatrecht"),
    _open("Was ist das Urheberrecht an KI-generierten Bildern?",
        ["Rechtlich nicht abschließend geregelt. Unklar, wem das Recht zusteht – Nutzer, Anbieter oder niemandem.",
         "In vielen Ländern: ohne menschliche Schöpfung kein Urheberrecht → potenziell gemeinfrei.",
         "International umstritten und wird zunehmend gerichtlich geklärt."],
        key_points=["ungeklärt", "menschliche Schöpfung", "gemeinfrei", "umstritten"], topic="KI-Urheberrecht"),
    _mc("Was ist ein Plagiat?", ["Fremde Leistung als eigene ausgeben ohne Quellenangabe", "Ein Design-Trend", "Eine Lizenzart", "Ein Druckverfahren"], 0, topic="Plagiat"),
    _mc("Was ist der Unterschied kommerziell/nicht-kommerziell?", ["Kommerziell = wirtschaftliche Tätigkeit/Gewinn. Nicht-kommerziell = privat/kein Gewinn", "Kein Unterschied", "Kommerziell = Print", "Nicht-kommerziell = digital"], 0, topic="Kommerziell"),
    _open("Warum ist Schutzrechte-Wissen für Mediengestalter wichtig?",
        ["Man arbeitet täglich mit Bildern, Schriften, Texten. Ohne Kenntnis riskiert man Urheberrechtsverletzungen.",
         "Man nutzt ständig fremde Werke und erstellt eigene. Schutzrechte-Wissen schützt vor Abmahnungen.",
         "Ob Stockfoto, Schriftlizenz oder Logo – falsche Entscheidungen haben rechtliche Konsequenzen."],
        key_points=["täglich", "Bilder", "Schriften", "Abmahnungen", "Konsequenzen"], topic="Relevanz Schutzrechte"),
    _open("Was ist eine Abmahnung?",
        ["Formelle Aufforderung, eine Rechtsverletzung zu unterlassen. Sofort Anwalt hinzuziehen.",
         "Aufforderung zum Stoppen rechtswidrigen Verhaltens + meist Schadensersatz.",
         "Ernst nehmen, nicht ignorieren. Unverzüglich rechtlichen Beistand suchen."],
        key_points=["formell", "Unterlassung", "Anwalt", "Schadensersatz"], topic="Abmahnung"),
    _tf("Open-Source-Schriften darf man immer kommerziell nutzen.", False,
        "Meistens ja, aber man muss die jeweilige Lizenz prüfen – es gibt unterschiedliche OS-Lizenzen.", topic="Open-Source Schriften"),
    _mc("Was ist ein eingetragenes Design?",
        ["Schützt die äußere Erscheinungsform eines Produkts, muss aktiv angemeldet werden",
         "Gleichbedeutend mit Urheberrecht", "Nur für Mode relevant", "Ein Computerprogramm"], 0, topic="Eingetragenes Design"),
    _tf("Das Urheberrecht muss in Deutschland registriert werden.", False,
        "Nein – es entsteht automatisch mit der Schöpfung.", topic="Urheberrecht-Registrierung"),
]


# ── U7: Korrekturen durchführen ──

U7_THEORY = (
    "**Korrekturen durchführen**\n\n"
    "**Korrekturzeichen:** DIN 16511 – genormte Zeichen für Einfügen, Löschen, Ersetzen, Absatz.\n\n"
    "**Korrekturworkflow:** Andruck/Proof → 1. Korrektur → Umsetzung → 2. Korrektur/Revision → Imprimatur → Druck.\n\n"
    "**Imprimatur:** Lateinisch 'Es werde gedruckt'. Offizielle Druckfreigabe durch den Kunden.\n\n"
    "**Digital:** PDF-Kommentare, InDesign-Cloud, Soft-Proof.\n\n"
    "**Typografische Fehler:** Hurenkind (letzte Zeile oben allein), Schusterjunge (erste Zeile unten allein)."
)

U7_QUIZ: List[Dict] = [
    _mc("Welcher Norm folgen Korrekturzeichen?", ["DIN 16511", "DIN A4", "ISO 9001", "DIN 16516"], 0, topic="DIN 16511"),
    _open("Wie werden Korrekturzeichen korrekt eingesetzt?",
        ["Im Text markieren wo der Fehler ist + am Rand das Korrekturzeichen mit Anweisung eintragen.",
         "Zwei Stellen: Fehlermarkierung im Text und Erklärung am Seitenrand.",
         "Fehlerhafte Stelle im Text markieren, Korrekturzeichen am Rand. Beide klar verbunden."],
        key_points=["im Text", "am Rand", "Zeichen", "verbunden"], topic="Korrekturzeichen-Einsatz"),
    _open("Was bedeutet Imprimatur?",
        ["Lateinisch 'Es werde gedruckt'. Schriftliche Druckfreigabe des Kunden.",
         "Offizielle Freigabe nach der letzten Korrektur – gibt den Auftrag zum Drucken.",
         "Abschließende Freigabe. Entbindet den Gestalter von der Haftung für spätere Fehler."],
        key_points=["Druckfreigabe", "Kunde", "schriftlich", "Latein"], topic="Imprimatur"),
    _open("Was ist eine Korrekturfahne?",
        ["Ausdruck des aktuellen Stands zur Kontrolle. Fehler werden markiert und zurückgegeben.",
         "Vorabversion zum Prüfen. Kunden/Lektoren tragen Korrekturen ein.",
         "Probeausdruck zur Überprüfung von Text und Layout vor dem Druck."],
        key_points=["Ausdruck", "Kontrolle", "Korrektur", "Vorabversion"], topic="Korrekturfahne"),
    _open("Was ist ein Soft-Proof?",
        ["Farbverbindliche Simulation des Druckergebnisses auf kalibriertem Monitor.",
         "Druckergebnis wird auf dem Bildschirm simuliert mit ICC-Farbprofil.",
         "Ersetzt physischen Proof durch digitale Farbsimulation – günstiger, schneller."],
        key_points=["Monitor", "kalibriert", "Simulation", "ICC-Profil"], topic="Soft-Proof"),
    _mc("Was ist eine Hurenkind-Zeile?", ["Letzte Zeile eines Absatzes allein am Beginn einer neuen Seite", "Erste Zeile allein am Seitenende", "Eine besonders kurze Zeile", "Ein Fehler in der Schrift"], 0, topic="Hurenkind"),
    _mc("Was ist eine Schusterjungen-Zeile?", ["Erste Zeile eines neuen Absatzes allein am Ende einer Seite", "Letzte Zeile allein oben", "Ein Druckfehler", "Eine Sonderzeile"], 0, topic="Schusterjunge"),
    _open("Was ist der Unterschied zwischen erster und zweiter Korrektur?",
        ["Erste: vollständige Fehlererfassung. Zweite: prüft ob Korrekturen richtig umgesetzt wurden.",
         "Erste Korrektur erfasst Fehler. Revisionskorrektur prüft die Korrekturdurchführung.",
         "Erste: alle Fehler finden. Zweite: kontrollieren dass keine neuen Fehler entstanden sind."],
        key_points=["erste", "Fehlererfassung", "zweite", "Revision", "Kontrolle"], topic="Korrekturschleifen"),
    _open("Wie werden digitale Korrekturen durchgeführt?",
        ["PDF-Kommentare in Acrobat, cloudbasierte InDesign-Funktionen.",
         "Per PDF-Annotation, E-Mail mit markierten Screenshots, Projektmanagement-Tools.",
         "Online-Proof-Systeme wie Filestage, bei denen Kunden direkt kommentieren."],
        key_points=["PDF", "Kommentare", "digital", "cloud"], topic="Digitale Korrektur"),
    _mc("Was wird beim Korrekturlesen typischerweise gefunden?",
        ["Rechtschreibung, falsche Abstände, Trennfehler, Bildpositionierung, CD-Abweichungen",
         "Nur Rechtschreibfehler", "Nur Farbfehler", "Nur technische Fehler"], 0, topic="Korrektur-Typen"),
    _open("Was ist der Unterschied zwischen Korrektur und Revision?",
        ["Korrektur = Fehlersuche. Revision = Prüfung ob Korrekturen richtig umgesetzt wurden.",
         "Korrektur identifiziert Fehler. Revision überprüft die Korrekturdurchführung.",
         "Korrektur = Fehleridentifikation, Revision = Qualitätssicherung der Korrektur."],
        key_points=["Korrektur", "Fehlersuche", "Revision", "Überprüfung"], topic="Korrektur vs. Revision"),
    _mc("Was ist eine Reinzeichnung?",
        ["Fertige, druckbereite Version nach allen Korrekturen", "Erste Skizze", "Handzeichnung", "Proof"], 0, topic="Reinzeichnung"),
    _open("Warum ist es wichtig, Korrekturen schriftlich zu dokumentieren?",
        ["Schriftliche Dokumentation schützt beide Seiten. Nachweisbar welche Änderungen beauftragt wurden.",
         "Mündliche Absprachen führen zu Missverständnissen. Schriftliches ist rechtlich belastbar.",
         "Schafft Verbindlichkeit und Transparenz, besonders wenn mehrere Personen beteiligt sind."],
        key_points=["schriftlich", "Nachweis", "rechtlich", "Verbindlichkeit"], topic="Dokumentation"),
    _open("Wie verändert KI den Korrekturprozess?",
        ["KI erkennt Rechtschreib-/Grammatikfehler automatisch. Ersetzt aber nicht menschliche inhaltliche Kontrolle.",
         "KI-Tools prüfen Texte automatisch. Im Layout: erste KI-Tools erkennen CD-Abweichungen.",
         "KI automatisiert Routinekorrekturen. Stilentscheidungen und inhaltliche Korrekturen bleiben menschlich."],
        key_points=["automatisch", "Routine", "menschlich", "inhaltlich"], topic="KI-Korrektur"),
    _open("Was ist Silbentrennung und warum ist sie wichtig?",
        ["Teilt Wörter am Zeilenende regelgerecht für gleichmäßige Abstände und ruhiges Schriftbild.",
         "Korrekte Trennung verbessert den Grauwert und vermeidet Lücken im Blocksatz.",
         "Fehlerhafte Trennungen können die Bedeutung verändern und müssen sorgfältig geprüft werden."],
        key_points=["Zeilenende", "Blocksatz", "Grauwert", "regelgerecht"], topic="Silbentrennung"),
    _mc("Wie viele Korrekturschleifen sind üblich?", ["2-3", "1", "10", "Keine"], 0, topic="Korrekturschleifen"),
    _open("Was ist ein Andruckbogen?",
        ["Erster Probedruck auf der echten Druckmaschine zur Farbkontrolle.",
         "Wird mit tatsächlichem Papier und Druckfarben hergestellt – genauestes Bild des Endprodukts.",
         "Erster Bogen der Druckmaschine, wird vom Drucker und ggf. Kunden abgenommen."],
        key_points=["Probedruck", "Druckmaschine", "Farbkontrolle", "echt"], topic="Andruckbogen"),
    _mc("Was ist Paginierung?", ["Seitennummerierung", "Farbkorrektur", "Schriftauswahl", "Bildbearbeitung"], 0, topic="Paginierung"),
    _open("Was ist ein Redaktionsschluss?",
        ["Termin, bis zu dem alle Inhalte und Korrekturen vorliegen müssen.",
         "Definiert wann keine Änderungen mehr akzeptiert werden – gibt Planungssicherheit.",
         "Ohne Redaktionsschluss gefährden Last-Minute-Änderungen den Produktionsablauf."],
        key_points=["Termin", "Inhalte", "keine Änderungen", "Planungssicherheit"], topic="Redaktionsschluss"),
    _tf("Das Imprimatur entbindet den Gestalter von der Haftung für Fehler, die der Kunde hätte sehen müssen.", True,
        "Nach Imprimatur liegt die Verantwortung beim Kunden, der die Freigabe erteilt hat.", topic="Imprimatur-Haftung"),
]


# ── U8: Protokolle ──

U8_THEORY = (
    "**Protokolle**\n\n"
    "**Zweck:** Dokumentation von Beschlüssen, Aufgaben, Vereinbarungen. Rechtliche Absicherung.\n\n"
    "**Arten:** Verlaufsprotokoll (wer hat was gesagt), Ergebnisprotokoll (nur Beschlüsse), "
    "Gedächtnisprotokoll (nachträglich).\n\n"
    "**Aufbau:** Datum, Ort, Teilnehmer, Thema, Inhalt, Aufgaben mit Zuständigkeiten, Unterschriften.\n\n"
    "**Zeitform:** Vergangenheitsform (Präteritum).\n\n"
    "**Wichtig für Mediengestalter:** Schützt vor 'Das haben wir nie so besprochen'-Situationen."
)

U8_QUIZ: List[Dict] = [
    _open("Was ist ein Protokoll und welchen Zweck erfüllt es?",
        ["Schriftliche Aufzeichnung einer Besprechung. Dokumentiert Beschlüsse und sichert rechtlich ab.",
         "Hält fest was besprochen und entschieden wurde. Schafft Verbindlichkeit.",
         "Verlässliches Gedächtnis für Besprechungen. Klärt Zuständigkeiten, schützt bei Meinungsverschiedenheiten."],
        key_points=["schriftlich", "Beschlüsse", "Verbindlichkeit", "rechtlich"], topic="Protokoll-Grundlagen"),
    _mc("Was ist der Unterschied Verlaufs- vs. Ergebnisprotokoll?",
        ["Verlauf: ganzer Ablauf chronologisch. Ergebnis: nur Beschlüsse und Aufgaben",
         "Kein Unterschied", "Verlauf ist kürzer", "Ergebnis ist für den Chef"], 0, topic="Protokollarten"),
    _mc("Welche Bestandteile gehören zwingend in ein Protokoll?",
        ["Datum, Ort, Teilnehmer, Thema, Inhalt, Aufgaben mit Zuständigkeiten",
         "Nur das Datum", "Nur die Unterschrift", "Nur die Aufgabenliste"], 0, topic="Protokoll-Bestandteile"),
    _open("Was ist ein Gedächtnisprotokoll?",
        ["Wird nachträglich aus dem Gedächtnis erstellt, wenn keine Mitschrift möglich war.",
         "Basiert auf der Erinnerung und kann daher lückenhaft sein.",
         "Sollte so schnell wie möglich nach der Besprechung verfasst werden."],
        key_points=["nachträglich", "Gedächtnis", "lückenhaft", "schnell"], topic="Gedächtnisprotokoll"),
    _open("Warum sind Protokolle im Kundenprozess besonders wichtig?",
        ["Schützen vor ungerechtfertigten Nachforderungen. Dokumentieren was vereinbart wurde.",
         "Schaffen Klarheit wer welche Aufgaben übernimmt und bis wann.",
         "Rechtliche Absicherung: dokumentieren Briefing, Korrekturen und Freigaben."],
        key_points=["Nachforderungen", "Klarheit", "rechtlich", "Absicherung"], topic="Protokoll-Relevanz"),
    _mc("In welcher Zeitform wird ein Protokoll verfasst?",
        ["Vergangenheitsform (Präteritum)", "Gegenwart", "Zukunft", "Konjunktiv"], 0, topic="Zeitform"),
    _open("Wie geht man mit Meinungsverschiedenheiten im Protokoll um?",
        ["Sachlich und neutral wiedergeben, ohne zu werten.",
         "Werden nicht ausgeblendet, aber sachlich formuliert. Fokus auf erzielte Ergebnisse.",
         "Neutral wiedergeben ohne eine Seite zu bevorzugen. Fokus auf das Resultat."],
        key_points=["sachlich", "neutral", "nicht werten", "Ergebnis"], topic="Meinungsverschiedenheiten"),
    _mc("Wann sollte ein Protokoll versandt werden?",
        ["Am selben oder folgenden Tag – idealerweise innerhalb 24-48h",
         "Nach einer Woche", "Erst wenn das Projekt fertig ist", "Gar nicht"], 0, topic="Versand-Timing"),
    _open("Was macht ein gutes Protokoll aus?",
        ["Vollständig, sachlich, klar strukturiert, zeitnah erstellt. Frei von Wertungen.",
         "Vollständigkeit, Neutralität, Übersichtlichkeit. Kein Raum für Interpretationen.",
         "Präzise und nachvollziehbar. Kurz genug um gelesen zu werden, vollständig genug als Quelle."],
        key_points=["vollständig", "sachlich", "strukturiert", "zeitnah"], topic="Gutes Protokoll"),
    _mc("Was sind 'offene Punkte'?",
        ["Unerledigte Aufgaben/ungeklärte Fragen, die weiterverfolgt werden müssen",
         "Punkte über die man nicht reden will", "Fragen die nie beantwortet werden", "Tagesordnungspunkte"], 0, topic="Offene Punkte"),
    _open("Was ist ein Aktionsplan und wie unterscheidet er sich vom Protokoll?",
        ["Komprimierte Aufgabenliste mit Verantwortlichen und Deadlines. Anhang zum Protokoll.",
         "Während Protokoll den Verlauf dokumentiert, ist der Aktionsplan eine kompakte To-do-Liste.",
         "Extrahiert die Aufgaben aus dem Protokoll in eine übersichtliche Liste."],
        key_points=["Aufgabenliste", "Verantwortliche", "Deadlines", "kompakt"], topic="Aktionsplan"),
    _open("Welche Fehler sollte man beim Protokollieren vermeiden?",
        ["Subjektive Meinungen, fehlende Zuständigkeiten, zu spätes Versenden, unvollständige Teilnehmerliste.",
         "Keine persönlichen Meinungen, keine wichtigen Punkte auslassen, nicht zu spät anfangen.",
         "Unvollständigkeit, Subjektivität, zu lang, fehlende Deadlines."],
        key_points=["subjektiv", "unvollständig", "zu spät", "fehlende Deadlines"], topic="Protokoll-Fehler"),
    _open("Wie hilft ein Protokoll bei der Projektkalkulation?",
        ["Dokumentiert Änderungswünsche. Mehraufwand nachweisbar für Rechnungsstellung.",
         "Zeigt wie viele Korrekturrunden vereinbart wurden. Wichtig für Nachkalkulation.",
         "Gedächtnis des Projekts: zeigt was vereinbart und was nachträglich geändert wurde."],
        key_points=["Änderungswünsche", "Nachkalkulation", "Nachweis", "Rechnungsstellung"], topic="Protokoll und Kalkulation"),
    _mc("Was ist eine Tagesordnung?",
        ["Liste der zu besprechenden Themen – bildet die Struktur des Protokolls",
         "Die Uhrzeit der Besprechung", "Ein Kalender", "Ein Ergebnisprotokoll"], 0, topic="Tagesordnung"),
    _open("Wie sichert ein Protokoll den Mediengestalter rechtlich ab?",
        ["Wenn der Kunde behauptet etwas nicht beauftragt zu haben, ist das Protokoll der Nachweis.",
         "Unterschriebenes/bestätigtes Protokoll ist ein rechtliches Dokument und Beweismittel.",
         "Dokumentiert Freigaben, Korrekturen und Änderungswünsche verbindlich."],
        key_points=["Nachweis", "Beweismittel", "Freigaben", "verbindlich"], topic="Rechtliche Absicherung"),
    _open("Wie werden digitale Protokolle in modernen Workflows genutzt?",
        ["Über E-Mail, Asana, Trello, Notion geteilt. Aufgaben direkt zuweisbar.",
         "Kollaborative Tools: Notion, Confluence, Google Docs. Direkt bearbeitbar und teilbar.",
         "Aufgaben direkt aus Protokoll in Projektmanagement-Tool übertragen. Spart Zeit."],
        key_points=["Notion", "Trello", "kollaborativ", "direkt zuweisen"], topic="Digitale Protokolle"),
    _mc("Was ist der Unterschied Beschluss- vs. Ergebnisprotokoll?",
        ["Beschluss: nur formale Abstimmungsergebnisse. Ergebnis: alle Ergebnisse und nächste Schritte",
         "Kein Unterschied", "Beschluss ist länger", "Ergebnis ist formeller"], 0, topic="Beschluss vs. Ergebnis"),
    _open("Was sollte nach dem Versand eines Protokolls getan werden?",
        ["Teilnehmer lesen und geben Rückmeldung. Nach Bestätigung gilt es als verbindlich.",
         "Aufgaben in Arbeitsablauf übernehmen. Beim nächsten Meeting offene Punkte prüfen.",
         "Von allen bestätigen lassen (Unterschrift oder E-Mail). Archivieren und als Referenz nutzen."],
        key_points=["Rückmeldung", "Bestätigung", "verbindlich", "archivieren"], topic="Nach Protokoll-Versand"),
    _tf("Der Protokollführer darf seine eigene Meinung ins Protokoll schreiben.", False,
        "Protokolle müssen sachlich und neutral sein – keine persönlichen Wertungen.", topic="Neutralität"),
    _mc("Was ist ein Beschlussprotokoll?",
        ["Dokumentiert ausschließlich formale Beschlüsse und Abstimmungsergebnisse",
         "Ein normales Ergebnisprotokoll", "Ein mündlicher Bericht", "Eine To-do-Liste"], 0, topic="Beschlussprotokoll"),
]


# ══════════════════════════════════════════════════════════════
# EXPORT: Alle Prüfungsthemen als Units
# ══════════════════════════════════════════════════════════════

IHK_PRUEFUNG_2026_UNITS = [
    {
        "id": "ihk-p26-u1", "title": "Corporate Design Beratung", "level": 3,
        "theory": U1_THEORY, "quiz": U1_QUIZ, "examples": [], "exercise": None,
        "tags": ["ihk", "prüfung2026", "corporate-design", "beratung"],
        "exam_area": "Medien konzipieren, gestalten und präsentieren",
        "fachrichtung": "alle",
    },
    {
        "id": "ihk-p26-u2", "title": "Zielgruppenanalyse", "level": 3,
        "theory": U2_THEORY, "quiz": U2_QUIZ, "examples": [], "exercise": None,
        "tags": ["ihk", "prüfung2026", "zielgruppe", "analyse"],
        "exam_area": "Medien konzipieren, gestalten und präsentieren",
        "fachrichtung": "alle",
    },
    {
        "id": "ihk-p26-u3", "title": "Logo-Entwurf", "level": 3,
        "theory": U3_THEORY, "quiz": U3_QUIZ, "examples": [], "exercise": None,
        "tags": ["ihk", "prüfung2026", "logo", "entwurf"],
        "exam_area": "Medien konzipieren, gestalten und präsentieren",
        "fachrichtung": "alle",
    },
    {
        "id": "ihk-p26-u4", "title": "Webseiten-Gestaltung", "level": 3,
        "theory": U4_THEORY, "quiz": U4_QUIZ, "examples": [], "exercise": None,
        "tags": ["ihk", "prüfung2026", "webdesign", "ux"],
        "exam_area": "Medien konzipieren, gestalten und präsentieren",
        "fachrichtung": "alle",
    },
    {
        "id": "ihk-p26-u5", "title": "Flyer-Gestaltung", "level": 3,
        "theory": U5_THEORY, "quiz": U5_QUIZ, "examples": [], "exercise": None,
        "tags": ["ihk", "prüfung2026", "flyer", "print"],
        "exam_area": "Medien konzipieren, gestalten und präsentieren",
        "fachrichtung": "alle",
    },
    {
        "id": "ihk-p26-u6", "title": "Schutzrechte", "level": 3,
        "theory": U6_THEORY, "quiz": U6_QUIZ, "examples": [], "exercise": None,
        "tags": ["ihk", "prüfung2026", "schutzrechte", "urheberrecht"],
        "exam_area": "Medien konzipieren, gestalten und präsentieren",
        "fachrichtung": "alle",
    },
    {
        "id": "ihk-p26-u7", "title": "Korrekturen durchführen", "level": 3,
        "theory": U7_THEORY, "quiz": U7_QUIZ, "examples": [], "exercise": None,
        "tags": ["ihk", "prüfung2026", "korrektur", "din16511"],
        "exam_area": "Medien konzipieren, gestalten und präsentieren",
        "fachrichtung": "alle",
    },
    {
        "id": "ihk-p26-u8", "title": "Protokolle", "level": 3,
        "theory": U8_THEORY, "quiz": U8_QUIZ, "examples": [], "exercise": None,
        "tags": ["ihk", "prüfung2026", "protokoll", "dokumentation"],
        "exam_area": "Medien konzipieren, gestalten und präsentieren",
        "fachrichtung": "alle",
    },
]

# Convenience: count totals
TOTAL_QUESTIONS = sum(len(u["quiz"]) for u in IHK_PRUEFUNG_2026_UNITS)
TOTAL_OPEN = sum(1 for u in IHK_PRUEFUNG_2026_UNITS for q in u["quiz"] if q["type"] == "open")
TOTAL_MC = sum(1 for u in IHK_PRUEFUNG_2026_UNITS for q in u["quiz"] if q["type"] == "mc")
TOTAL_TF = sum(1 for u in IHK_PRUEFUNG_2026_UNITS for q in u["quiz"] if q["type"] == "tf")
