<?php
/**
 * Ailey Portal — Auth Helper
 * 
 * Session management, login/register, whitelist check.
 */

class PortalAuth {
    private array $config;
    
    /** Max failed login attempts before lockout */
    private const MAX_LOGIN_ATTEMPTS = 5;
    /** Lockout duration in seconds (15 minutes) */
    private const LOGIN_LOCKOUT_SECONDS = 900;
    
    public function __construct(array $config) {
        $this->config = $config;
    }
    
    // ── Session Start ────────────────────────────────────────────────
    public function initSession(): void {
        $sc = $this->config['session'];
        session_name($sc['cookie_name']);
        session_set_cookie_params([
            'lifetime' => $sc['lifetime'],
            'path'     => '/',
            'secure'   => $sc['secure'],
            'httponly'  => $sc['httponly'],
            'samesite' => $sc['samesite'],
        ]);
        if (session_status() === PHP_SESSION_NONE) {
            session_start();
        }
    }
    
    // ── Get Current User ─────────────────────────────────────────────
    public function getCurrentUser(): ?array {
        $token = $_SESSION['auth_token'] ?? $_COOKIE['ailey_portal_token'] ?? null;
        if (!$token) return null;
        
        $tokenHash = hash('sha256', $token);
        $session = PortalDB::getSessionByToken($tokenHash);
        
        if (!$session) {
            // Session expired or invalid — clear stale token
            unset($_SESSION['auth_token']);
            return null;
        }
        
        if ($session['user_status'] !== 'active') {
            $this->logout();
            return null;
        }
        
        return [
            'id'             => $session['user_id'],
            'email'          => $session['email'],
            'display_name'   => $session['display_name'],
            'role'           => $session['role'],
            'user_tier'      => $session['user_tier'] ?? 'invited',
            'avatar_url'     => $session['avatar_url'] ?? null,
            'bio'            => $session['bio'] ?? null,
            'equipped_badge' => $session['equipped_badge'] ?? null,
        ];
    }
    
    // ── Register ─────────────────────────────────────────────────────
    public function register(string $email, string $displayName, string $password, string $ip): array {
        $email = strtolower(trim($email));
        
        // Validate
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            return ['success' => false, 'error' => 'Ungültige E-Mail-Adresse.'];
        }
        if (strlen($displayName) < 2 || strlen($displayName) > 50) {
            return ['success' => false, 'error' => 'Name muss 2-50 Zeichen lang sein.'];
        }
        if (strlen($password) < 8) {
            return ['success' => false, 'error' => 'Passwort muss mindestens 8 Zeichen haben.'];
        }
        
        // Check whitelist
        if (!PortalDB::isWhitelisted($email)) {
            return ['success' => false, 'error' => 'Diese E-Mail ist nicht eingeladen. Das Ailey Portal ist aktuell nur auf Einladung zugänglich.'];
        }
        
        // Check if user exists
        if (PortalDB::getUserByEmail($email)) {
            return ['success' => false, 'error' => 'Ein Account mit dieser E-Mail existiert bereits.'];
        }
        
        // Create user
        $hash = password_hash($password, PASSWORD_BCRYPT, ['cost' => 12]);
        $userId = PortalDB::createUser($email, $displayName, $hash);
        PortalDB::markWhitelistUsed($email);
        
        // Log consent
        PortalDB::logConsent($userId, 'dsgvo', 'Datenschutzeinwilligung bei Registrierung erteilt.', $ip);
        PortalDB::logConsent($userId, 'ki_disclosure', 'KI-Kennzeichnung zur Kenntnis genommen.', $ip);
        
        // Update consent timestamps
        $stmt = PortalDB::get()->prepare('UPDATE portal_users SET consent_dsgvo = NOW(), consent_ki = NOW() WHERE id = ?');
        $stmt->execute([$userId]);
        
        // Create session
        $token = $this->createSessionToken($userId, $ip);
        
        PortalDB::logAdmin('user_registered', null, $userId, "Email: $email", $ip);
        
        return ['success' => true, 'user_id' => $userId, 'token' => $token];
    }

    // ── Register (Public — open, no whitelist) ───────────────────────
    public function registerPublic(string $email, string $displayName, string $password, string $ip): array {
        $email = strtolower(trim($email));

        // Validate
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            return ['success' => false, 'error' => 'Ungültige E-Mail-Adresse.'];
        }
        if (strlen($displayName) < 2 || strlen($displayName) > 50) {
            return ['success' => false, 'error' => 'Name muss 2-50 Zeichen lang sein.'];
        }
        if (strlen($password) < 8) {
            return ['success' => false, 'error' => 'Passwort muss mindestens 8 Zeichen haben.'];
        }

        // Check if user exists
        if (PortalDB::getUserByEmail($email)) {
            return ['success' => false, 'error' => 'Ein Account mit dieser E-Mail existiert bereits.'];
        }

        // Create user with public tier (no whitelist required)
        $hash = password_hash($password, PASSWORD_BCRYPT, ['cost' => 12]);
        $userId = PortalDB::createUser($email, $displayName, $hash, 'public');

        // Log consent
        PortalDB::logConsent($userId, 'dsgvo', 'Datenschutzeinwilligung bei Registrierung erteilt.', $ip);
        PortalDB::logConsent($userId, 'ki_disclosure', 'KI-Kennzeichnung zur Kenntnis genommen.', $ip);
        PortalDB::logConsent($userId, 'agb', 'Nutzungsbedingungen bei Registrierung akzeptiert.', $ip);

        $stmt = PortalDB::get()->prepare('UPDATE portal_users SET consent_dsgvo = NOW(), consent_ki = NOW() WHERE id = ?');
        $stmt->execute([$userId]);

        $token = $this->createSessionToken($userId, $ip);

        PortalDB::logAdmin('user_registered_public', null, $userId, "Email: $email (public tier)", $ip);

        return ['success' => true, 'user_id' => $userId, 'token' => $token, 'tier' => 'public'];
    }
    
    // ── Login ────────────────────────────────────────────────────────
    public function login(string $email, string $password, string $ip): array {
        $email = strtolower(trim($email));
        
        // ── Brute-force protection ──────────────────────────────
        $attempts = $this->getRecentLoginAttempts($email, $ip);
        if ($attempts >= self::MAX_LOGIN_ATTEMPTS) {
            $lockoutMin = intval(self::LOGIN_LOCKOUT_SECONDS / 60);
            return ['success' => false, 'error' => "Zu viele Anmeldeversuche. Bitte warte $lockoutMin Minuten."];
        }
        
        $user = PortalDB::getUserByEmail($email);
        
        if (!$user || !password_verify($password, $user['password_hash'])) {
            $this->logLoginAttempt($email, $ip, false);
            // Generic error — don't reveal whether email exists
            return ['success' => false, 'error' => 'E-Mail oder Passwort falsch.'];
        }
        
        if ($user['status'] !== 'active') {
            return ['success' => false, 'error' => 'Dein Account ist deaktiviert.'];
        }
        
        // Successful login — clear failed attempts
        $this->clearLoginAttempts($email, $ip);
        
        // Create session
        $token = $this->createSessionToken($user['id'], $ip);
        
        return ['success' => true, 'user_id' => $user['id'], 'token' => $token];
    }
    
    // ── Logout ───────────────────────────────────────────────────────
    public function logout(): void {
        $token = $_SESSION['auth_token'] ?? $_COOKIE['ailey_portal_token'] ?? null;
        if ($token) {
            PortalDB::deleteSession(hash('sha256', $token));
        }
        $_SESSION = [];
        if (ini_get('session.use_cookies')) {
            $p = session_get_cookie_params();
            setcookie(session_name(), '', time() - 42000, $p['path'], $p['domain'], $p['secure'], $p['httponly']);
        }
        setcookie('ailey_portal_token', '', time() - 42000, '/');
        session_destroy();
    }
    
    // ── Session Token ────────────────────────────────────────────────
    private function createSessionToken(string $userId, string $ip): string {
        $token = bin2hex(random_bytes(32));
        $tokenHash = hash('sha256', $token);
        $lifetime = $this->config['session']['lifetime'];
        $device = $_SERVER['HTTP_USER_AGENT'] ?? 'Unknown';
        
        PortalDB::createSession($userId, $tokenHash, $lifetime, substr($device, 0, 500), $ip);
        
        // Store in session AND cookie
        $_SESSION['auth_token'] = $token;
        setcookie('ailey_portal_token', $token, [
            'expires'  => time() + $lifetime,
            'path'     => '/',
            'secure'   => $this->config['session']['secure'],
            'httponly'  => $this->config['session']['httponly'],
            'samesite' => $this->config['session']['samesite'],
        ]);
        
        return $token;
    }
    
    // ── Brute-Force Protection ───────────────────────────────────────
    /**
     * Count recent failed login attempts for email+IP combination.
     * Uses the portal_admin_log table (action='login_failed').
     */
    private function getRecentLoginAttempts(string $email, string $ip): int {
        $cutoff = date('Y-m-d H:i:s', time() - self::LOGIN_LOCKOUT_SECONDS);
        $db = PortalDB::get();
        $stmt = $db->prepare(
            'SELECT COUNT(*) FROM portal_admin_log 
             WHERE action = ? AND details = ? AND ip_address = ? AND created_at > ?'
        );
        $stmt->execute(['login_failed', $email, $ip, $cutoff]);
        return (int) $stmt->fetchColumn();
    }
    
    private function logLoginAttempt(string $email, string $ip, bool $success): void {
        $action = $success ? 'login_success' : 'login_failed';
        PortalDB::logAdmin($action, null, null, $email, $ip);
    }
    
    private function clearLoginAttempts(string $email, string $ip): void {
        $db = PortalDB::get();
        $stmt = $db->prepare(
            'DELETE FROM portal_admin_log WHERE action = ? AND details = ? AND ip_address = ?'
        );
        $stmt->execute(['login_failed', $email, $ip]);
    }
    
    // ── Admin Check ──────────────────────────────────────────────────
    public function isAdmin(): bool {
        $user = $this->getCurrentUser();
        return $user && $user['role'] === 'admin';
    }

    // ── Password Reset — Request ─────────────────────────────────────
    /**
     * Generate a password-reset token and send it via email.
     * Always returns a generic success message (don't reveal if email exists).
     */
    public function requestPasswordReset(string $email, string $ip): array {
        $email = strtolower(trim($email));

        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            return ['success' => true, 'message' => 'Falls ein Account mit dieser E-Mail existiert, erhältst du einen Reset-Link.'];
        }

        $user = PortalDB::getUserByEmail($email);

        // Always return same message — don't reveal whether the account exists
        if (!$user || $user['status'] !== 'active') {
            return ['success' => true, 'message' => 'Falls ein Account mit dieser E-Mail existiert, erhältst du einen Reset-Link.'];
        }

        // Rate limit: max 3 resets per hour per user
        $recent = PortalDB::countRecentPasswordResets($user['id']);
        if ($recent >= 3) {
            return ['success' => true, 'message' => 'Falls ein Account mit dieser E-Mail existiert, erhältst du einen Reset-Link.'];
        }

        // Generate token
        $token = PortalDB::createPasswordResetToken($user['id']);

        // Build reset URL
        $baseUrl = rtrim($this->config['site']['url'] ?? 'https://ask-ailey.sexngears.de', '/');
        $resetUrl = $baseUrl . '/reset-password?token=' . urlencode($token);

        // Send email
        $subject = 'A!ley Portal — Passwort zurücksetzen';
        $displayName = htmlspecialchars($user['display_name'] ?? 'User');
        $body = <<<HTML
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body style="font-family:system-ui,-apple-system,sans-serif;background:#0a0a0a;color:#e5e5e5;padding:2rem;">
<div style="max-width:480px;margin:0 auto;background:#1a1a2e;border-radius:12px;padding:2rem;border:1px solid #333;">
    <div style="text-align:center;margin-bottom:1.5rem;">
        <h2 style="color:#a78bfa;margin:0;">A!ley Portal</h2>
        <p style="color:#888;font-size:0.9rem;">Passwort zurücksetzen</p>
    </div>
    <p>Hey {$displayName},</p>
    <p>Du (oder jemand anderes) hat einen Passwort-Reset für deinen Account angefordert.</p>
    <p style="text-align:center;margin:1.5rem 0;">
        <a href="{$resetUrl}" style="display:inline-block;background:#a78bfa;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;">
            Neues Passwort setzen
        </a>
    </p>
    <p style="font-size:0.85rem;color:#888;">Dieser Link ist <strong>1 Stunde</strong> gültig. Falls du den Reset nicht angefordert hast, ignoriere diese E-Mail einfach.</p>
    <hr style="border:none;border-top:1px solid #333;margin:1.5rem 0;">
    <p style="font-size:0.75rem;color:#666;">Falls der Button nicht funktioniert, kopiere diesen Link:<br>
    <a href="{$resetUrl}" style="color:#a78bfa;word-break:break-all;">{$resetUrl}</a></p>
</div>
</body></html>
HTML;

        $headers  = "From: A!ley Portal <noreply@sexngears.de>\r\n";
        $headers .= "Reply-To: noreply@sexngears.de\r\n";
        $headers .= "MIME-Version: 1.0\r\n";
        $headers .= "Content-Type: text/html; charset=UTF-8\r\n";

        @mail($email, $subject, $body, $headers);

        PortalDB::logAdmin('password_reset_requested', null, $user['id'], "Email: $email", $ip);

        return ['success' => true, 'message' => 'Falls ein Account mit dieser E-Mail existiert, erhältst du einen Reset-Link.'];
    }

    // ── Password Reset — Execute ─────────────────────────────────────
    /**
     * Validate token and set a new password.
     */
    public function resetPassword(string $token, string $newPassword, string $ip): array {
        if (strlen($newPassword) < 8) {
            return ['success' => false, 'error' => 'Passwort muss mindestens 8 Zeichen haben.'];
        }

        $reset = PortalDB::getValidPasswordReset($token);
        if (!$reset) {
            return ['success' => false, 'error' => 'Der Reset-Link ist ungültig oder abgelaufen. Bitte fordere einen neuen an.'];
        }

        // Update password
        $hash = password_hash($newPassword, PASSWORD_BCRYPT, ['cost' => 12]);
        PortalDB::updateUserPassword($reset['user_id'], $hash);

        // Mark token as used
        PortalDB::markPasswordResetUsed($token);

        // Invalidate all existing sessions for this user (security: force re-login)
        PortalDB::get()->prepare('DELETE FROM portal_sessions WHERE user_id = ?')
            ->execute([$reset['user_id']]);

        PortalDB::logAdmin('password_reset_completed', null, $reset['user_id'], "Email: " . $reset['email'], $ip);

        return ['success' => true, 'message' => 'Passwort erfolgreich geändert! Du kannst dich jetzt einloggen.'];
    }
    
    // ── Require Auth (redirect if not logged in) ─────────────────────
    public function requireAuth(): array {
        $user = $this->getCurrentUser();
        if (!$user) {
            // If this is an API call, return JSON error instead of redirect
            $isApi = str_contains($_SERVER['REQUEST_URI'] ?? '', 'api.php')
                  || str_contains($_SERVER['SCRIPT_NAME'] ?? '', 'api.php');
            if ($isApi) {
                http_response_code(401);
                echo json_encode(['error' => 'not_authenticated']);
                exit;
            }
            header('Location: /login');
            exit;
        }
        return $user;
    }
    
    public function requireAdmin(): array {
        $user = $this->requireAuth();
        if ($user['role'] !== 'admin') {
            http_response_code(403);
            echo 'Zugriff verweigert.';
            exit;
        }
        return $user;
    }
}
