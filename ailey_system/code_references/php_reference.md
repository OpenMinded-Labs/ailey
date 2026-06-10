# PHP — Ailey Code-Referenz

> Modernes PHP 8.1+ mit Strict Types, Enums, Fibers, Readonly Properties

## Projekt-Struktur (PSR-4)

```
project/
├── public/
│   └── index.php          # Entry point
├── src/
│   ├── Controller/
│   ├── Model/
│   ├── Service/
│   └── Middleware/
├── tests/
├── config/
├── templates/             # oder views/
├── composer.json
├── .env
└── .htaccess
```

## PHP 8.1+ Features

```php
<?php
declare(strict_types=1);

// Enums (8.1+)
enum Status: string {
    case Active   = 'active';
    case Inactive = 'inactive';
    case Pending  = 'pending';
    
    public function label(): string {
        return match($this) {
            self::Active   => 'Aktiv',
            self::Inactive => 'Inaktiv',
            self::Pending  => 'Ausstehend',
        };
    }
}

// Readonly Properties (8.1+)
class User {
    public function __construct(
        public readonly int $id,
        public readonly string $name,
        public readonly string $email,
        private readonly \DateTimeImmutable $createdAt = new \DateTimeImmutable(),
    ) {}
}

// Named Arguments
$user = new User(id: 1, name: 'Simon', email: 'simon@example.com');

// Match Expression (statt switch)
$result = match($status) {
    'active'   => handleActive(),
    'inactive' => handleInactive(),
    default    => throw new \InvalidArgumentException("Unknown status: $status"),
};

// Null-safe Operator
$country = $user?->getAddress()?->getCountry()?->getName();

// Fibers (8.1+, Async-Grundlage)
$fiber = new \Fiber(function (): void {
    $value = \Fiber::suspend('first');
    echo "Resumed with: $value";
});
$result = $fiber->start(); // 'first'
$fiber->resume('second');
```

## PDO (Datenbank)

```php
<?php
// Verbindung
$pdo = new \PDO(
    'mysql:host=localhost;dbname=mydb;charset=utf8mb4',
    username: $user,
    password: $pass,
    options: [
        \PDO::ATTR_ERRMODE            => \PDO::ERRMODE_EXCEPTION,
        \PDO::ATTR_DEFAULT_FETCH_MODE => \PDO::FETCH_ASSOC,
        \PDO::ATTR_EMULATE_PREPARES   => false,
    ]
);

// Prepared Statements (IMMER verwenden — nie Variablen direkt in SQL!)
$stmt = $pdo->prepare('SELECT * FROM users WHERE email = :email AND status = :status');
$stmt->execute(['email' => $email, 'status' => 'active']);
$users = $stmt->fetchAll();

// Insert
$stmt = $pdo->prepare('INSERT INTO users (name, email) VALUES (:name, :email)');
$stmt->execute(['name' => $name, 'email' => $email]);
$id = $pdo->lastInsertId();

// Transaction
$pdo->beginTransaction();
try {
    $pdo->prepare('UPDATE accounts SET balance = balance - ? WHERE id = ?')->execute([$amount, $from]);
    $pdo->prepare('UPDATE accounts SET balance = balance + ? WHERE id = ?')->execute([$amount, $to]);
    $pdo->commit();
} catch (\Exception $e) {
    $pdo->rollBack();
    throw $e;
}
```

## REST API (Vanilla PHP)

```php
<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

$method = $_SERVER['REQUEST_METHOD'];
$path   = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);

match(true) {
    $method === 'GET' && $path === '/api/items'
        => getItems(),
    $method === 'POST' && $path === '/api/items'
        => createItem(),
    default
        => respond(404, ['error' => 'Not found']),
};

function getItems(): void {
    respond(200, ['items' => [], 'count' => 0]);
}

function createItem(): void {
    $data = json_decode(file_get_contents('php://input'), true) ?? [];
    $name = trim($data['name'] ?? '');
    if ($name === '') {
        respond(400, ['error' => 'Name fehlt']);
        return;
    }
    respond(201, ['success' => true, 'item' => ['name' => $name]]);
}

function respond(int $code, array $data): void {
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}
```

## Composer & Autoloading

```json
{
    "require": {
        "php": ">=8.1",
        "vlucas/phpdotenv": "^5.6"
    },
    "require-dev": {
        "phpunit/phpunit": "^10.0",
        "phpstan/phpstan": "^1.10"
    },
    "autoload": {
        "psr-4": {
            "App\\": "src/"
        }
    }
}
```

```bash
composer install
composer require package/name
composer dump-autoload
```

## Sicherheit

```php
// XSS — IMMER escapen bei HTML-Output
echo htmlspecialchars($userInput, ENT_QUOTES, 'UTF-8');

// SQL Injection — IMMER Prepared Statements
$stmt = $pdo->prepare('SELECT * FROM users WHERE id = ?');
$stmt->execute([$id]); // NIE: "... WHERE id = $id"

// CSRF Token
$token = bin2hex(random_bytes(32));
$_SESSION['csrf_token'] = $token;
// Im Formular: <input type="hidden" name="csrf" value="<?= $token ?>">
// Beim Verarbeiten: hash_equals($_SESSION['csrf_token'], $_POST['csrf'])

// Password Hashing
$hash = password_hash($password, PASSWORD_DEFAULT);
$valid = password_verify($input, $hash);

// Input Validation
$email = filter_var($input, FILTER_VALIDATE_EMAIL);
$int   = filter_var($input, FILTER_VALIDATE_INT);
```

## Testing (PHPUnit)

```php
<?php
declare(strict_types=1);

use PHPUnit\Framework\TestCase;

class UserServiceTest extends TestCase {
    public function testCreateUser(): void {
        $service = new UserService();
        $user = $service->create('Test', 'test@example.com');
        $this->assertInstanceOf(User::class, $user);
        $this->assertSame('Test', $user->name);
    }
    
    public function testInvalidEmailThrows(): void {
        $this->expectException(\InvalidArgumentException::class);
        (new UserService())->create('Test', 'invalid');
    }
}
```

## Häufige Stolperfallen

- `declare(strict_types=1);` vergessen → Type Coercion statt TypeError
- `==` statt `===` → "0" == false ist true, "0" === false ist false
- `htmlspecialchars()` vergessen → XSS-Lücke
- Array-Funktionen mischen: `array_map` vs `array_filter` vs `array_reduce`
- `empty()` ist gefährlich: `empty("0")` ist true
- Composer Autoloading nicht generiert → `composer dump-autoload`
- `php://input` kann nur einmal gelesen werden
