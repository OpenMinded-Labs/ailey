<?php
/**
 * A!ley Portal — Impressum (Legal requirement, TMG §5)
 */
require_once __DIR__ . '/layout.php';
portal_head('Impressum', isPublic: true);
$imp = $config['site']['impressum'] ?? [];
$lbl = $config['label'] ?? [];
$lblActive = !empty($lbl['active']);
$lblName = $lbl['name'] ?? 'OpenM!nded';
?>

<div class="legal-page">
    <a href="/chat" class="legal-back">← Zurück</a>

    <h1>Impressum</h1>

    <h2>Angaben gemäß § 5 TMG</h2>
    <p>
        <?= htmlspecialchars($imp['name'] ?? 'Simon van de Loo') ?><br>
        <?php if ($lblActive): ?>
            <?= htmlspecialchars($lblName) ?><?php if (!empty($lbl['tagline'])): ?> — <?= htmlspecialchars($lbl['tagline']) ?><?php endif; ?><br>
        <?php endif; ?>
        <?= nl2br(htmlspecialchars($imp['address'] ?? '')) ?>
    </p>

    <?php if ($lblActive): ?>
    <p>
        <em>A!ley ist ein Projekt unter dem Label <?= htmlspecialchars($lblName) ?>.
        <?php if (empty($lbl['is_company'])): ?>
        <?= htmlspecialchars($lblName) ?> ist derzeit kein eingetragenes Unternehmen;
        verantwortlich im Sinne des Gesetzes ist die oben genannte natürliche Person.
        <?php endif; ?></em>
    </p>
    <?php endif; ?>

    <h2>Kontakt</h2>
    <p>
        <?php if (!empty($imp['email'])): ?>
            E-Mail: <?= htmlspecialchars($imp['email']) ?><br>
        <?php endif; ?>
        <?php if (!empty($imp['phone'])): ?>
            Telefon: <?= htmlspecialchars($imp['phone']) ?><br>
        <?php endif; ?>
    </p>

    <h2>Verantwortlich für den Inhalt (§ 18 Abs. 2 MStV)</h2>
    <p>
        <?= htmlspecialchars($imp['name'] ?? 'Simon van de Loo') ?><br>
        <?= nl2br(htmlspecialchars($imp['address'] ?? '')) ?>
    </p>

    <h2>KI-Kennzeichnung (EU AI Act)</h2>
    <p>
        <?= htmlspecialchars($config['site']['ki_disclosure'] ?? '') ?>
    </p>
    <p>
        Dieses Portal nutzt ein lokal betriebenes KI-System namens „A!ley". 
        Alle Antworten werden in Echtzeit von einem Large Language Model generiert 
        und stellen keine professionelle Beratung (medizinisch, rechtlich, psychologisch) dar. 
        Der Betreiber übernimmt keine Haftung für KI-generierte Inhalte.
    </p>

    <h2>Streitschlichtung</h2>
    <p>
        Die Europäische Kommission stellt eine Plattform zur Online-Streitbeilegung (OS) bereit:
        <a href="https://ec.europa.eu/consumers/odr/" target="_blank" rel="noopener">
            https://ec.europa.eu/consumers/odr/
        </a>.<br>
        Wir sind nicht bereit oder verpflichtet, an Streitbeilegungsverfahren vor einer 
        Verbraucherschlichtungsstelle teilzunehmen.
    </p>
</div>

<?php portal_footer(); ?>
