<?php
/**
 * A!ley Portal — Nutzungsbedingungen (AGB / Terms of Service)
 */
require_once __DIR__ . '/layout.php';
portal_head('Nutzungsbedingungen', isPublic: true);
?>

<div class="legal-page">
    <a href="/" class="legal-back">← Zurück</a>

    <h1>Nutzungsbedingungen</h1>
    <p><strong>Stand: Juli 2025</strong></p>

    <h2>1. Geltungsbereich</h2>
    <p>Diese Nutzungsbedingungen gelten für die Nutzung des A!ley Portals unter <a href="https://hey-ailey.com">hey-ailey.com</a> (sowie der weiterhin erreichbaren Adresse <a href="https://ask-ailey.sexngears.de">ask-ailey.sexngears.de</a>). Betreiber ist Simon van de Loo (siehe <a href="/impressum">Impressum</a>). Mit der Registrierung akzeptierst du diese Bedingungen.</p>

    <h2>2. Registrierung & Account-Typen</h2>
    <p>Das Portal bietet zwei Registrierungstypen:</p>
    <ul>
        <li><strong>Invited (Eingeladen):</strong> Voller Zugang zu Chat, Bild-/Songgeneration, Forum, Galerie und allen Features. Erfordert eine Einladung.</li>
        <li><strong>Public (Öffentlich):</strong> Zugang zu Forum, Galerie, Blog, Bewertungen und Kommentaren. Kein Zugang zum Chat oder zu Bild-/Songgeneration.</li>
    </ul>
    <p>Jeder Nutzer darf nur einen Account erstellen. Die Weitergabe von Zugangsdaten ist nicht gestattet.</p>

    <h2>3. V$ (Virtuelle Währung)</h2>
    <p>V$ ist eine virtuelle Währung innerhalb des Portals. V$ haben keinen realen Geldwert und können nicht ausgezahlt, übertragen oder verkauft werden. V$ dienen ausschließlich zur Nutzung von Portal-Features:</p>
    <ul>
        <li>Chat-Nachrichten: 0.2-2 V$ je nach Modus</li>
        <li>Bildgenerierung: 15 V$</li>
        <li>Songgenerierung: 30 V$</li>
    </ul>
    <p>V$ können durch aktive Teilnahme (Bewertungen, Kommentare, Forum-Beiträge) verdient werden. Wöchentlich erhalten aktive Nutzer ein Guthaben-Topup basierend auf ihrem Tier.</p>

    <h2>4. Verhaltensregeln</h2>
    <p>Folgende Inhalte und Verhaltensweisen sind untersagt:</p>
    <ul>
        <li>Beleidigungen, Hassrede, Diskriminierung</li>
        <li>Sexuell explizite oder gewaltverherrlichende Inhalte</li>
        <li>Spam, Werbung, Phishing</li>
        <li>Manipulation des V$-Systems oder anderer Mechanismen</li>
        <li>Veröffentlichung persönlicher Daten Dritter</li>
        <li>Verstoß gegen geltendes Recht</li>
    </ul>
    <p>Verstöße führen zu Verwarnungen und können bis zur Sperrung des Accounts führen. Das Warnsystem ist gestuft (Level 0-3). Bei Level 3 wird der Account deaktiviert.</p>

    <h2>5. KI-generierte Inhalte</h2>
    <p>A!ley ist ein KI-System. Alle von A!ley generierten Texte, Bilder und Songs sind KI-generiert und entsprechend gekennzeichnet. Die generierten Inhalte können Fehler enthalten und stellen keine professionelle Beratung dar.</p>
    <p>Mit der Nutzung des Chats stimmst du zu, dass deine Eingaben zur Verbesserung der KI-Erfahrung verarbeitet werden können (siehe <a href="/datenschutz">Datenschutzerklärung</a>).</p>

    <h2>6. Nutzungsrechte an generierten Inhalten</h2>
    <p>Bilder und Songs, die du über das Portal generierst, werden in der öffentlichen Galerie geteilt und können von anderen Nutzern bewertet und kommentiert werden. Du erhältst ein einfaches Nutzungsrecht an den von dir generierten Inhalten, der Betreiber behält sich ein uneingeschränktes Nutzungsrecht vor (z.B. für die Galerie, Blog, Marketing).</p>

    <h2>7. Forum</h2>
    <p>Im Forum können registrierte Nutzer (Invited & Public) Beiträge und Kommentare verfassen. Der Betreiber behält sich vor, Inhalte ohne Vorankündigung zu entfernen oder Themen zu sperren. A!ley kann automatisiert im Forum antworten — diese Antworten sind als KI-generiert gekennzeichnet.</p>

    <h2>8. Haftungsausschluss</h2>
    <p>Das Portal wird "as is" bereitgestellt. Der Betreiber übernimmt keine Garantie für Verfügbarkeit, Fehlerfreiheit oder Eignung für bestimmte Zwecke. Die Nutzung erfolgt auf eigene Verantwortung.</p>

    <h2>9. Änderungen</h2>
    <p>Der Betreiber behält sich vor, diese Nutzungsbedingungen jederzeit zu ändern. Wesentliche Änderungen werden über das Portal kommuniziert. Die weitere Nutzung nach einer Änderung gilt als Zustimmung.</p>

    <h2>10. Schlussbestimmungen</h2>
    <p>Es gilt das Recht der Bundesrepublik Deutschland. Sollten einzelne Bestimmungen unwirksam sein, bleiben die übrigen Bestimmungen unberührt.</p>
</div>

<?php portal_footer(); ?>
