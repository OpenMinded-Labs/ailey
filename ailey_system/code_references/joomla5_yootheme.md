# Technische Referenz: Joomla 5 & YOOtheme Pro

> Diese Referenz dient als Nachschlagewerk für Ailey im Code-Modus.
> Sie wird automatisch eingebunden, wenn ein Projekt Joomla- oder YOOtheme-Code enthält.

---

## 1. Joomla 5 — Architektur & Grundprinzipien

### 1.1 Core Philosophie

Joomla 5 basiert auf modernen PHP-Standards:
- **PHP ≥ 8.1** (strict typing)
- **PSR-4 Autoloading** via Namespaces
- **Dependency Injection** (DI-Container) statt globaler Factories
- **Jede PHP-Datei** beginnt mit `declare(strict_types=1);`
- Code liegt im Unterordner `/src`, nicht mehr im Extension-Root

### 1.2 Dependency Injection Container

**Legacy (VERMEIDEN):**
```php
$db = \JFactory::getDbo(); // ❌ Deprecated
```

**Modern (VERWENDEN):**
```php
use Joomla\CMS\Factory;

$container = Factory::getContainer();
$db  = $container->get('DatabaseDriver');
$app = $container->get('SiteApplication');
```

Oder besser: Über Konstruktor-Injection in der eigenen Klasse.

### 1.3 Datenbank-Zugriff (Query Builder)

```php
$db = Factory::getContainer()->get('DatabaseDriver');
$query = $db->getQuery(true);

$query->select($db->quoteName(['a.id', 'a.title']))
    ->from($db->quoteName('#__content', 'a'))
    ->where($db->quoteName('a.state') . ' = 1')
    ->order($db->quoteName('a.created') . ' DESC');

$db->setQuery($query);
$results = $db->loadObjectList();
```

**Wichtige Tabellen:**
| Tabelle | Inhalt |
|---------|--------|
| `#__content` | Artikeldaten |
| `#__extensions` | Installierte Erweiterungen |
| `#__fields_values` | Custom-Field-Werte |
| `#__menu` | Menüpunkte & Routing |
| `#__categories` | Kategorien |
| `#__users` | Benutzerdaten |

> `#__` wird automatisch durch das konfigurierte Tabellen-Prefix ersetzt.

---

## 2. Extension-Entwicklung

Alle Joomla 5 Extensions **müssen** eine `services/provider.php` besitzen.

### 2.1 Module

Zweck: Darstellung kleinerer Datenblöcke (z.B. Sidebar-Widgets).

**Dateistruktur:**
```
mod_example/
├── mod_example.xml              # Manifest
├── services/
│   └── provider.php             # Service Provider (obligatorisch)
├── src/
│   ├── Dispatcher/
│   │   └── Dispatcher.php       # Logik / Dispatch
│   └── Helper/
│       └── ExampleHelper.php    # Datenbeschaffung
└── tmpl/
    └── default.php              # Template/Output
```

**Manifest (Auszug):**
```xml
<namespace path="src">MyVendor\Module\Example</namespace>
```

Module nutzen in J5 einen `Dispatcher`, der vom `ModuleDispatcherFactory` geladen wird.

### 2.2 Plugins (Event Subscriber)

Plugins implementieren das `SubscriberInterface` — sie erweitern **nicht** mehr `JPlugin`.

**Dateistruktur:**
```
plg_content_example/
├── example.xml
├── services/
│   └── provider.php
└── src/
    └── Extension/
        └── Example.php
```

**Code Pattern:**
```php
<?php
declare(strict_types=1);

namespace MyVendor\Plugin\Content\Example\Extension;

use Joomla\Event\SubscriberInterface;
use Joomla\CMS\Plugin\CMSPlugin;

class Example extends CMSPlugin implements SubscriberInterface
{
    public static function getSubscribedEvents(): array
    {
        return [
            'onContentPrepare' => 'prepareContent',
        ];
    }

    public function prepareContent($event): void
    {
        $article = $event->getArgument(0);
        $params  = $event->getArgument(1);
        // Logik hier
    }
}
```

### 2.3 Komponenten (MVC)

Striktes Model-View-Controller Muster:
- **Controller**: Input verarbeiten (`$input->get()`)
- **Model**: Datenlogik (`getListQuery()`, `getItem()`)
- **View**: Daten aufbereiten (`HtmlView` für Frontend, `JsonView` für API)
- **Router**: SEF-URLs in `src/Service/Router.php`

---

## 3. Frontend Assets (Web Asset Manager)

**Keine** manuellen `<script>` oder `<link>` Tags! Joomla 5 nutzt den WAM.

**Definition** (`joomla.asset.json` im Extension-Root):
```json
{
  "assets": [
    {
      "name": "mod_example.script",
      "type": "script",
      "uri": "mod_example/example.js",
      "dependencies": ["core"],
      "attributes": {"defer": true},
      "version": "1.0.0"
    }
  ]
}
```

**Aufruf im PHP:**
```php
use Joomla\CMS\Factory;

$wa = Factory::getApplication()->getDocument()->getWebAssetManager();
$wa->useScript('mod_example.script');
$wa->useStyle('mod_example.style');
```

---

## 4. YOOtheme Pro Integration

YOOtheme Pro ist ein Page-Builder-Framework **über** Joomla. Eigene Entwicklungen laufen immer über ein **Child-Theme**.

### 4.1 Pfade & Child Theme

```
/templates/yootheme_child/
├── bootstrap.php          # Haupteinstiegspunkt für PHP-Logik
├── builder/               # Custom Builder-Elemente
│   └── meinelement/
│       ├── element.json   # Konfiguration & Felder
│       └── template.php   # Rendering
├── css/
│   └── custom.css         # Custom Styles
└── ...
```

### 4.2 Custom Builder Elemente

**element.json** (Konfiguration & Felder):
```json
{
    "name": "my_element",
    "title": "Mein Element",
    "icon": "bolt",
    "group": "multiple",
    "fields": {
        "title": {
            "label": "Titel",
            "type": "text"
        },
        "content": {
            "label": "Inhalt",
            "type": "editor"
        },
        "image": {
            "label": "Bild",
            "type": "image"
        }
    }
}
```

**template.php** (Rendering):
```php
<?php
$el = $this->el('div', [
    'class' => ['el-element', 'uk-card', 'uk-card-body']
]);

$title = $props['title']
    ? $this->el('h3', ['class' => 'uk-card-title'], $props['title'])
    : null;
?>
<?= $el($props, $attrs) ?>
    <?php if ($title) : ?>
        <?= $title($props) ?>
    <?php endif ?>
    <div class="uk-margin"><?= $props['content'] ?></div>
<?= $el->end() ?>
```

### 4.3 Registrierung von Custom Elements

In `bootstrap.php` des Child-Themes:
```php
<?php
use YOOtheme\Builder;

return [
    'events' => [
        'builder.init' => function (Builder $builder) {
            $builder->addTypePath(__DIR__ . '/builder');
        },
    ],
];
```

### 4.4 UIkit 3 (CSS Framework)

YOOtheme basiert vollständig auf **UIkit 3** — kein Bootstrap, kein Tailwind!

**Wichtige Klassen:**
| Zweck | Klasse |
|-------|--------|
| Grid | `uk-grid` + Attribut `uk-grid` |
| Flex | `uk-flex`, `uk-flex-middle`, `uk-flex-center` |
| Card | `uk-card`, `uk-card-default`, `uk-card-body` |
| Margin | `uk-margin`, `uk-margin-small-top`, `uk-margin-large` |
| Padding | `uk-padding`, `uk-padding-small` |
| Text | `uk-text-center`, `uk-text-bold`, `uk-text-muted` |
| Visibility | `uk-visible@m`, `uk-hidden@s` |
| Width | `uk-width-1-2`, `uk-width-1-3@m` |
| Section | `uk-section`, `uk-section-default` |
| Container | `uk-container`, `uk-container-small` |
| Animation | `uk-animation-fade`, `uk-scrollspy` |

**Grid Beispiel:**
```html
<div class="uk-grid uk-child-width-1-3@m" uk-grid>
    <div>Spalte 1</div>
    <div>Spalte 2</div>
    <div>Spalte 3</div>
</div>
```

**Custom CSS:** Gehört in `custom.css` des Child-Themes oder im YOOtheme "Custom Code" Bereich.

### 4.5 Dynamic Content (Sources)

Für eigene Datenbank-Tabellen oder API-Daten als "Dynamic Source":

1. Listener auf `source.init` Event registrieren
2. Type-Definition erstellen (GraphQL-Schema-ähnlich)
3. Query-Definition (Resolver) implementieren

Dies erfordert die `YOOtheme\Builder\Source` Klassenstruktur.

---

## 5. Regeln für Code-Generierung

Wenn Code für Joomla 5 / YOOtheme generiert wird:

1. **Immer Namespaces** verwenden (`Vendor\Extension\Type`)
2. **Keine Legacy-Klassen** (`JFactory`, `JDocument`, `JTable` etc.)
3. **UIkit 3** für Frontend-HTML — keine Bootstrap-Klassen
4. **Sicherheit**: Inputs casten/filtern, Outputs escapen (`$this->escape($var)`)
5. **`services/provider.php`** ist obligatorisch für alle Extensions
6. **`declare(strict_types=1);`** in jeder PHP-Datei
7. **Prepared Statements** oder Query Builder für Datenbankzugriffe
8. **Web Asset Manager** für JS/CSS — keine manuellen Tags
9. **Event Subscriber Pattern** für Plugins
10. **Child-Theme** für YOOtheme-Anpassungen — niemals Core-Dateien ändern
