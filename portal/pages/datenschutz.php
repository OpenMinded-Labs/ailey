<?php
/**
 * A!ley Portal — Datenschutzerklärung (DSGVO)
 */
require_once __DIR__ . '/layout.php';
portal_head('Datenschutz', isPublic: true);
$imp = $config['site']['impressum'] ?? [];
$siteName = $config['site']['name'] ?? 'A!ley Portal';
$lbl = $config['label'] ?? [];
$lblActive = !empty($lbl['active']);
$lblName = $lbl['name'] ?? 'OpenM!nded';
?>

<div class="legal-page">
    <a href="/chat" class="legal-back">← Zurück</a>

    <h1>Datenschutzerklärung</h1>
    <p><em>Stand: Juli 2025</em></p>

    <h2>1. Verantwortlicher</h2>
    <p>
        <?= htmlspecialchars($imp['name'] ?? 'Simon van de Loo') ?><br>
        <?php if ($lblActive): ?>
            <?= htmlspecialchars($lblName) ?> (Label/Projekt)<br>
        <?php endif; ?>
        <?= nl2br(htmlspecialchars($imp['address'] ?? '')) ?><br>
        <?php if (!empty($imp['email'])): ?>
            E-Mail: <?= htmlspecialchars($imp['email']) ?>
        <?php endif; ?>
    </p>
    <?php if ($lblActive && empty($lbl['is_company'])): ?>
    <p>
        <em>Hinweis: A!ley erscheint unter dem Label „<?= htmlspecialchars($lblName) ?>".
        Verantwortlicher im Sinne der DSGVO ist die oben genannte natürliche Person.</em>
    </p>
    <?php endif; ?>

    <h2>2. Welche Daten wir erheben</h2>
    <p>Bei der Nutzung von <?= htmlspecialchars($siteName) ?> werden folgende Daten verarbeitet:</p>
    <p>
        <strong>Account-Daten:</strong> E-Mail-Adresse, Anzeigename, verschlüsseltes Passwort (bcrypt), Account-Typ (Invited/Public).<br>
        <strong>Profil-Daten:</strong> Profilbild (automatisch auf 200×200px verkleinert, gespeichert als WebP), Bio-Text, ausgerüstetes Badge.<br>
        <strong>Chat-Daten:</strong> Deine Nachrichten und A!leys Antworten, Gesprächstitel, Zusammenfassungen.<br>
        <strong>Chat-Bewertungen:</strong> Deine Bewertungen (👍/👎) und optionalen Kommentare zu KI-Antworten, zusammen mit dem Kontext der bewerteten Nachricht. Diese Daten können zur Verbesserung des KI-Systems verwendet werden.<br>
        <strong>Forum-Daten:</strong> Deine Beiträge, Antworten und Likes im Forum.<br>
        <strong>Galerie-Daten:</strong> Deine Bewertungen und Kommentare zu Galerie-Inhalten.<br>
        <strong>V$-Daten:</strong> Dein virtuelles Guthaben, Transaktionshistorie (Ein-/Ausgaben).<br>
        <strong>Achievement-Daten:</strong> Freigeschaltete Badges/Achievements und deren Zeitstempel.<br>
        <strong>Generierte Inhalte:</strong> Von dir angefragte Bilder und Songs, die in der Galerie veröffentlicht werden.<br>
        <strong>Technische Daten:</strong> IP-Adresse, User-Agent, Session-Token, Zeitstempel.<br>
        <strong>Einwilligungen:</strong> Zeitpunkt und Art deiner Datenschutz-Einwilligungen.
    </p>

    <h2>3. Zweck der Verarbeitung</h2>
    <p>
        Deine Daten werden ausschließlich für den Betrieb des Portals verwendet:
        Authentifizierung, Gesprächsführung mit der KI, Kontextspeicherung für bessere Antworten,
        V$-Wirtschaft (virtuelle Währung), Forum-Betrieb, Galerie-Interaktionen,
        Profildarstellung (Profilbild, Badge), Gamification (Achievements/Badges)
        und zur Einhaltung gesetzlicher Pflichten (DSGVO, TMG).
    </p>

    <h2>3a. Nutzung für KI-Verbesserung</h2>
    <p>
        Deine Eingaben im Chat können anonymisiert zur Verbesserung der KI-Erfahrung und zur 
        Feinabstimmung des A!ley-Systems verwendet werden. Dazu zählen auch deine Bewertungen 
        (👍/👎) und Kommentare zu KI-Antworten, die zusammen mit dem Nachrichtenkontext als 
        Trainingsgrundlage dienen können. Dabei werden keine personenbezogenen Daten 
        (Name, E-Mail) in Trainingsdaten aufgenommen — nur die anonymisierten Nachrichteninhalte. 
        Mit der Registrierung stimmst du dieser Nutzung zu. Du kannst diese Zustimmung jederzeit 
        widerrufen, indem du den Support kontaktierst oder dein Konto löschst.
    </p>

    <h2>3b. Nutzungsrechte an generierten Inhalten</h2>
    <p>
        Bilder und Songs, die du über das Portal generierst, werden in der öffentlichen Galerie 
        des Portals geteilt. Der Betreiber behält sich ein uneingeschränktes Nutzungsrecht an 
        diesen Inhalten vor (einschließlich Galerie, Blog, Promotion, Social Media). 
        Du erhältst ein einfaches Nutzungsrecht für private Zwecke. 
        Siehe auch die <a href="/agb">Nutzungsbedingungen</a>.
    </p>

    <h2>4. KI-System (Art. 13 EU AI Act)</h2>
    <p>
        <?= htmlspecialchars($config['site']['ki_disclosure'] ?? '') ?>
    </p>
    <p>
        Das KI-System „A!ley" läuft auf lokaler, dedizierter Hardware des Betreibers. 
        Deine Nachrichten werden <strong>nicht an Drittanbieter</strong> (OpenAI, Google, etc.) gesendet. 
        Die KI-Verarbeitung findet vollständig auf dem Server des Betreibers statt.
    </p>
    <p>
        Die KI speichert Zusammenfassungen vergangener Gespräche, um kontextbezogen antworten zu können. 
        Diese werden bei Löschung deines Accounts vollständig entfernt.
    </p>

    <h2>5. Rechtsgrundlage</h2>
    <p>
        Die Verarbeitung erfolgt auf Grundlage deiner Einwilligung (Art. 6 Abs. 1 lit. a DSGVO), 
        die du bei der Registrierung erteilst. Du kannst deine Einwilligung jederzeit widerrufen.
    </p>

    <h2>6. Speicherdauer</h2>
    <p>
        Deine Daten werden gespeichert, solange dein Account aktiv ist. 
        Nach Löschung deines Accounts werden alle personenbezogenen Daten innerhalb von 30 Tagen entfernt,
        einschließlich Profilbild, Bio, Achievements, Chat-Bewertungen und Forum-Beiträge.
        Anonymisierte Nutzungsstatistiken und bereits exportierte Trainingsdaten können länger gespeichert werden.
    </p>

    <h2>7. Deine Rechte (DSGVO)</h2>
    <p>Du hast folgende Rechte:</p>
    <p>
        <strong>Auskunft (Art. 15):</strong> Du kannst jederzeit Auskunft über deine gespeicherten Daten verlangen.<br>
        <strong>Berichtigung (Art. 16):</strong> Unrichtige Daten können korrigiert werden.<br>
        <strong>Löschung (Art. 17):</strong> Du kannst die Löschung deiner Daten verlangen — 
        nutze dafür die „Daten löschen"-Funktion in den Einstellungen.<br>
        <strong>Einschränkung (Art. 18):</strong> Du kannst die Einschränkung der Verarbeitung verlangen.<br>
        <strong>Datenübertragbarkeit (Art. 20):</strong> Du kannst deine Daten in maschinenlesbarer Form erhalten.<br>
        <strong>Widerspruch (Art. 21):</strong> Du kannst der Verarbeitung widersprechen.<br>
        <strong>Beschwerde:</strong> Du hast das Recht, dich bei einer Aufsichtsbehörde zu beschweren.
    </p>

    <h2>8. Hosting</h2>
    <p>
        Das Portal wird bei <strong>allinkl.com</strong> (ALL-INKL.COM - Neue Medien Münnich, Hauptstraße 68, 
        02742 Friedersdorf, Deutschland) gehostet. 
        Die Datenverarbeitung erfolgt in Deutschland.
    </p>

    <h2>9. Verbindung zum KI-Server</h2>
    <p>
        Die Kommunikation zwischen dem Portal und dem KI-Server erfolgt verschlüsselt (HTTPS). 
        Der KI-Server ruft regelmäßig neue Nachrichten vom Portal ab und sendet Antworten zurück. 
        Es werden keine Drittanbieter-Dienste für die Verbindung eingesetzt.
    </p>

    <h2>10. Cookies</h2>
    <p>
        Wir verwenden ausschließlich technisch notwendige Cookies für die Session-Verwaltung 
        und Theme-Speicherung. Es werden <strong>keine Tracking-Cookies</strong> oder 
        Analyse-Tools von Drittanbietern eingesetzt.
    </p>

    <h2>11. Keine Weitergabe an Dritte</h2>
    <p>
        Deine Daten werden nicht an Dritte verkauft oder zu Werbezwecken weitergegeben. 
        Eine Weitergabe erfolgt nur, wenn gesetzlich vorgeschrieben.
    </p>

    <h2>12. Minderjährige</h2>
    <p>
        Dieses Portal richtet sich an Personen ab 16 Jahren. 
        Jüngere Nutzer benötigen die Einwilligung eines Erziehungsberechtigten.
    </p>
</div>

<?php portal_footer(); ?>
