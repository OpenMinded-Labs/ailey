<?php
/**
 * Ailey Portal — API Router (Polling Architecture — No Tunnel Required)
 * 
 * Architecture:
 *   User sends message → stored in portal_offline_queue as "pending"
 *   Ailey Core polls ?action=poll_pending → gets pending jobs
 *   Ailey Core pushes result via ?action=push_reply
 *   User polls ?action=check_reply → gets response when ready
 * 
 * Actions:
 *   AUTH:     login, register, logout, me
 *   CHAT:     conversations, new_conversation, delete_conversation
 *             messages, send_message, check_reply
 *   POLLING:  poll_pending, push_reply, push_summary (Ailey Core → allinkl)
 *   ADMIN:    admin_users, admin_stats, admin_whitelist_add, admin_suspend_user
 *   DSGVO:    delete_my_data
 */

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

$configPath = __DIR__ . '/config.php';
if (!file_exists($configPath)) {
    http_response_code(500);
    echo json_encode(['error' => 'config.php not found']);
    exit;
}

$config = require $configPath;
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/nsfw_filter.php';

PortalDB::connect($config['db']);
PortalDB::checkDailyReset();   // ← auto-reset images/songs/messages counters once per day
$auth = new PortalAuth($config);
$auth->initSession();

// Probabilistic cleanup: ~1% of requests clean expired sessions + old login attempts + soft-deletes
if (random_int(1, 100) === 1) {
    PortalDB::cleanExpiredSessions();
    try {
        PortalDB::get()->exec(
            "DELETE FROM portal_admin_log WHERE action = 'login_failed' AND created_at < DATE_SUB(NOW(), INTERVAL 1 DAY)"
        );
    } catch (\Exception $e) { /* ignore */ }
    // Purge soft-deleted conversations & artifacts older than 30 days
    try {
        PortalDB::purgeExpiredSoftDeletes(30);
    } catch (\Exception $e) { /* ignore — table migration may not have run yet */ }
    // Clean expired password-reset tokens
    try {
        PortalDB::get()->exec(
            "DELETE FROM portal_password_resets WHERE expires_at < NOW() OR used = 1"
        );
    } catch (\Exception $e) { /* ignore — table may not exist yet */ }
    // Weekly V$ topup check
    try {
        PortalDB::checkWeeklyVdollarsTopup();
    } catch (\Exception $e) { /* ignore */ }
}

$action = $_GET['action'] ?? $_POST['action'] ?? '';
$ip = $_SERVER['REMOTE_ADDR'] ?? '';

$input = [];
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $raw = file_get_contents('php://input');
    $input = json_decode($raw, true) ?: [];
}

function verifyPortalKey(array $config): bool {
    $key = $_SERVER['HTTP_X_PORTAL_KEY'] ?? '';
    $expected = $config['ailey']['portal_key'] ?? '';
    if (!$expected) return false;
    return hash_equals($expected, $key);
}

try {
    switch ($action) {
        // ═══════════════════ AUTH ═════════════════════════════════
        case 'register':
            echo json_encode($auth->register(
                $input['email'] ?? '', $input['display_name'] ?? '',
                $input['password'] ?? '', $ip
            ));
            break;
        case 'register_public':
            echo json_encode($auth->registerPublic(
                $input['email'] ?? '', $input['display_name'] ?? '',
                $input['password'] ?? '', $ip
            ));
            break;
        case 'login':
            echo json_encode($auth->login($input['email'] ?? '', $input['password'] ?? '', $ip));
            break;
        case 'logout':
            $auth->logout();
            echo json_encode(['success' => true]);
            break;

        // ── Password Reset ──────────────────────────────────────
        case 'request_password_reset':
            echo json_encode($auth->requestPasswordReset($input['email'] ?? '', $ip));
            break;
        case 'reset_password':
            echo json_encode($auth->resetPassword($input['token'] ?? '', $input['password'] ?? '', $ip));
            break;

        case 'me':
            $user = $auth->getCurrentUser();
            echo json_encode($user
                ? ['success' => true, 'user' => $user]
                : ['success' => false, 'error' => 'not_authenticated']);
            break;

        // ═══════════════════ CONVERSATIONS ═══════════════════════
        case 'conversations':
            $user = $auth->requireAuth();
            echo json_encode(['success' => true, 'conversations' => PortalDB::listConversations($user['id'])]);
            break;
        case 'new_conversation':
            $user = $auth->requireAuth();
            echo json_encode(['success' => true, 'conversation_id' => PortalDB::createConversation($user['id'])]);
            break;
        case 'delete_conversation':
            $user = $auth->requireAuth();
            $convId = $input['conversation_id'] ?? '';
            if (!$convId) { echo json_encode(['error' => 'conversation_id required']); break; }
            $isAdmin = ($user['role'] === 'admin');
            echo json_encode(['success' => PortalDB::deleteConversation($convId, $user['id'], $isAdmin)]);
            break;
        case 'delete_artifact':
            $user = $auth->requireAuth();
            $artId = $input['artifact_id'] ?? '';
            if (!$artId) { echo json_encode(['error' => 'artifact_id required']); break; }
            $isAdmin = ($user['role'] === 'admin');
            echo json_encode(['success' => PortalDB::deleteArtifact($artId, $user['id'], $isAdmin)]);
            break;

        // ═══════════════════ MESSAGES ════════════════════════════
        case 'messages':
            $user = $auth->requireAuth();
            $convId = $_GET['conversation_id'] ?? '';
            if (!$convId) { echo json_encode(['error' => 'conversation_id required']); break; }
            $conv = PortalDB::getConversation($convId, $user['id']);
            if (!$conv) { echo json_encode(['error' => 'not_found']); break; }
            echo json_encode(['success' => true, 'messages' => PortalDB::getMessages($convId), 'conversation' => $conv]);
            break;

        // ─── send_message: Store msg + create queue job ─────────
        case 'send_message':
            $user = $auth->requireAuth();

            // Public-tier users cannot use chat
            if (PortalDB::getUserTier($user['id']) === 'public') {
                echo json_encode(['error' => 'tier_restricted', 'message' => 'Chat ist nur für eingeladene Nutzer verfügbar. Upgrade dein Konto oder nutze das Forum!']);
                break;
            }

            $message = trim($input['message'] ?? '');
            $convId = $input['conversation_id'] ?? '';

            if (!$message) { echo json_encode(['error' => 'message required']); break; }

            // ── Ban check: if user is currently banned, reject with ban info ──
            $warningInfo = PortalDB::getWarningInfo($user['id']);
            if ($warningInfo['banned']) {
                $bannedUntil = $warningInfo['banned_until'];
                $level = $warningInfo['level'];
                $reason = $warningInfo['reason'] ?? 'Wiederholtes Fehlverhalten';
                if ($level >= 5) {
                    $banMsg = "Du bist dauerhaft gesperrt. Grund: $reason. Schreibe eine Entschuldigung an kontakt@sexngears.de — Ailey entscheidet, ob sie dir verzeiht. 💜";
                } else {
                    $remaining = max(0, strtotime($bannedUntil) - time());
                    if ($remaining > 86400) {
                        $timeStr = round($remaining / 86400) . ' Tage';
                    } elseif ($remaining > 3600) {
                        $timeStr = round($remaining / 3600) . ' Stunden';
                    } else {
                        $timeStr = ceil($remaining / 60) . ' Minuten';
                    }
                    $banMsg = "Ailey antwortet dir gerade nicht. Du bist noch für $timeStr gesperrt (Stufe $level). Grund: $reason.";
                }
                echo json_encode([
                    'error' => 'banned',
                    'message' => $banMsg,
                    'banned_until' => $bannedUntil,
                    'warning_level' => $level,
                ]);
                break;
            }

            $limits = PortalDB::getEffectiveLimits($config['limits'] ?? []);
            if (mb_strlen($message) > $limits['max_message_length']) {
                echo json_encode(['error' => 'message_too_long']);
                break;
            }

            // Rate limit
            $rates = PortalDB::getRateCounts($user['id']);
            $maxH = $limits['max_hourly'];
            $maxD = $limits['max_daily'];
            if ($rates['hourly'] >= $maxH) {
                echo json_encode(['error' => 'rate_limited', 'message' => "Max $maxH Nachrichten pro Stunde."]);
                break;
            }
            if ($rates['daily'] >= $maxD) {
                echo json_encode(['error' => 'rate_limited', 'message' => "Max $maxD Nachrichten pro Tag."]);
                break;
            }

            // Chat mode: resolve BEFORE V$ spend so cost is mode-aware
            $chatMode = $input['chat_mode'] ?? 'thinking';
            if (!in_array($chatMode, ['hamster', 'ultrafast', 'flash', 'nitro', 'normal', 'thinking', 'light', 'focus'], true)) {
                $chatMode = 'thinking';
            }
            // Migrate old frontend values
            if ($chatMode === 'ultrafast') $chatMode = 'hamster';
            if ($chatMode === 'light') $chatMode = 'focus';
            if ($chatMode === 'flash') $chatMode = 'nitro';  // Flash → Nitro rename

            // V$ cost per chat mode (kept low so users actually chat)
            $modeCosts = [
                'hamster'  => 0.2,
                'nitro'    => 0.5,
                'normal'   => 1,
                'focus'    => 2,
                'thinking' => 2,
            ];
            $chatCost = $modeCosts[$chatMode] ?? 1;

            // V$ cost for chat message (mode-dependent)
            if (!PortalDB::spendVdollars($user['id'], $chatCost, "chat_message:{$chatMode}")) {
                $vInfo = PortalDB::getVdollarsInfo($user['id']);
                echo json_encode([
                    'error' => 'insufficient_vdollars',
                    'message' => "Nicht genug V$! Du hast nur {$vInfo['balance']} V$, brauchst aber {$chatCost} V$ für {$chatMode}.",
                    'balance' => $vInfo['balance'],
                    'cost' => $chatCost,
                    'mode' => $chatMode,
                ]);
                break;
            }

            // Track active day for V$ weekly topup calculation
            PortalDB::trackVdollarsActiveDay($user['id']);

            // Check if Ailey is offline/sleeping → instant away-message
            $aileyStatus = PortalDB::getAileyStatus();
            $isAway = in_array($aileyStatus, ['offline', 'sleeping'], true);

            // Create or verify conversation
            if (!$convId) {
                $convId = PortalDB::createConversation($user['id']);
            } else {
                if (!PortalDB::getConversation($convId, $user['id'])) {
                    echo json_encode(['error' => 'not_found']);
                    break;
                }
            }

            // Store user message
            $isFirst = (PortalDB::getConversation($convId, $user['id'])['message_count'] ?? 0) == 0;
            PortalDB::addMessage($convId, 'user', $message);
            PortalDB::updateConversation($convId);
            PortalDB::updateUserActivity($user['id']);

            // ── Away-message: if Ailey is offline/sleeping, respond instantly ──
            if ($isAway) {
                $lang = $user['language'] ?? 'de';
                $awayReply = ($lang === 'en')
                    ? "I'm not available right now — I'm either sleeping or my system is offline. 🌙\n\nYour message has been saved! I'll read it as soon as I'm back. Feel free to write more — I'll find everything here when I return. 💜"
                    : "Ich bin gerade nicht erreichbar — ich schlafe entweder oder mein System ist offline. 🌙\n\nDeine Nachricht ist gespeichert! Ich lese sie, sobald ich wieder da bin. Schreib ruhig weiter — ich finde alles hier, wenn ich zurückkomme. 💜";

                PortalDB::addMessage($convId, 'assistant', $awayReply, 'sleeping');
                PortalDB::updateConversation($convId);

                // Set a title for new conversations
                if ($isFirst) {
                    PortalDB::updateConversationTitle($convId, mb_substr($message, 0, 60));
                }

                echo json_encode([
                    'success'         => true,
                    'conversation_id' => $convId,
                    'queue_id'        => null,
                    'status'          => 'away',
                    'reply'           => $awayReply,
                    'mood'            => 'sleeping',
                    'title'           => $isFirst ? mb_substr($message, 0, 60) : null,
                ]);
                break;
            }

            // Collect context
            $history = PortalDB::getRecentMessages($convId, 20);
            $summary = PortalDB::getConversationSummary($convId);
            $conv = PortalDB::getConversation($convId, $user['id']);
            $hasTitle = !empty($conv['title']) && $conv['title'] !== 'Neues Gespräch';

            // Fetch cross-session user memories
            $userMemories = PortalDB::getUserMemories($user['id'], 20);

            // Image URL (uploaded via upload_chat_file before send_message)
            $imageUrl = $input['image_url'] ?? null;
            if ($imageUrl && !filter_var($imageUrl, FILTER_VALIDATE_URL)) {
                $imageUrl = null; // Reject invalid URLs
            }

            // Document/file URL (uploaded via upload_chat_file before send_message)
            $fileUrl = $input['file_url'] ?? null;
            $fileType = $input['file_type'] ?? null; // 'image' or 'document'
            $fileName = $input['file_name'] ?? null;
            if ($fileUrl && !filter_var($fileUrl, FILTER_VALIDATE_URL)) {
                $fileUrl = null;
            }

            // Create queue job (Ailey Core will pick this up via poll_pending)
            $queueId = PortalDB::addToOfflineQueue(
                $user['id'], $convId, $message,
                json_encode([
                    'user_name'            => $user['display_name'],
                    'user_email'           => $user['email'],
                    'glossary_id'          => $user['glossary_id'] ?? null,
                    'custom_instructions'  => PortalDB::getUserPreferences($user['id']),
                    'web_search'           => !empty($input['web_search']),
                    'chat_mode'            => $chatMode,
                    'image_url'            => $imageUrl,
                    'file_url'             => $fileUrl,
                    'file_type'            => $fileType,
                    'file_name'            => $fileName,
                    'history'              => $history,
                    'summary'              => $summary ?? '',
                    'user_memories'        => $userMemories,
                    'language'             => $user['language'] ?? 'de',
                    'is_first_message'     => $isFirst,
                    'has_title'            => $hasTitle,
                    'message_count'        => ($conv['message_count'] ?? 0),
                ])
            );

            // Check achievements (non-blocking, catches errors)
            $newBadges = [];
            try { $newBadges = PortalDB::checkAndUnlockAchievements($user['id']); } catch (\Exception $e) {}

            echo json_encode([
                'success'         => true,
                'conversation_id' => $convId,
                'queue_id'        => $queueId,
                'status'          => 'pending',
                'new_badges'      => $newBadges,
            ]);
            break;

        // ─── check_reply: User polls for Ailey's response ───────
        case 'check_reply':
            $user = $auth->requireAuth();
            $queueId = $_GET['queue_id'] ?? $input['queue_id'] ?? '';
            if (!$queueId) { echo json_encode(['error' => 'queue_id required']); break; }

            $item = PortalDB::getOfflineItem($queueId, $user['id']);
            if (!$item) { echo json_encode(['error' => 'not_found']); break; }

            if ($item['status'] === 'done' && $item['reply']) {
                $suggestionsArr = [];
                if (!empty($item['suggestions'])) {
                    $decoded = json_decode($item['suggestions'], true);
                    if (is_array($decoded)) $suggestionsArr = $decoded;
                }
                // Load thinking/reasoning content from cache
                $thinkingContent = null;
                $thinkDir = __DIR__ . '/uploads/thinking_cache';
                $safeId2 = preg_replace('/[^a-zA-Z0-9_-]/', '', $queueId);
                $thinkFile = $thinkDir . '/' . $safeId2 . '.txt';
                if (is_file($thinkFile)) {
                    $thinkingContent = file_get_contents($thinkFile);
                    if (strlen(trim($thinkingContent)) < 5) $thinkingContent = null;
                }
                // Load interactive flag from cache
                $hasInteractive = false;
                $interDir = __DIR__ . '/uploads/interactive_cache';
                $interFile = $interDir . '/' . $safeId2 . '.flag';
                if (is_file($interFile)) {
                    $hasInteractive = true;
                }
                // Load song_detected JSON from cache
                $songDetected = null;
                $songDir = __DIR__ . '/uploads/song_detect';
                $songFile = $songDir . '/' . $safeId2 . '.json';
                if (is_file($songFile)) {
                    $decoded = json_decode(file_get_contents($songFile), true);
                    if (is_array($decoded) && !empty($decoded['is_song'])) {
                        $songDetected = $decoded;
                    }
                }
                $responseData = [
                    'success' => true,
                    'status'  => 'done',
                    'reply'   => $item['reply'],
                    'mood'    => $item['mood'] ?? 'neutral',
                    'title'   => $item['conversation_title'] ?? null,
                    'suggestions' => $suggestionsArr,
                ];
                if ($thinkingContent) {
                    $responseData['thinking'] = $thinkingContent;
                }
                if ($hasInteractive) {
                    $responseData['has_interactive'] = true;
                }
                if (!empty($item['image_url'])) {
                    $responseData['image_url'] = $item['image_url'];
                }
                if ($songDetected) {
                    $responseData['song_detected'] = $songDetected;
                    $responseData['queue_id'] = $queueId; // needed for request_song
                }
                echo json_encode($responseData);
            } elseif ($item['status'] === 'failed') {
                echo json_encode([
                    'success' => false,
                    'status'  => 'failed',
                    'message' => 'Ailey konnte nicht antworten. Versuch es nochmal! 💜',
                ]);
            } elseif ($item['status'] === 'cancelled') {
                echo json_encode([
                    'success' => true,
                    'status'  => 'cancelled',
                ]);
            } else {
                // Still pending/processing — check for partial reply
                $partialReply = null;
                $cacheDir = __DIR__ . '/uploads/partial_cache';
                $safeId = preg_replace('/[^a-zA-Z0-9_-]/', '', $queueId);
                $cacheFile = $cacheDir . '/' . $safeId . '.txt';
                if (is_file($cacheFile)) {
                    $partialReply = file_get_contents($cacheFile);
                    if (strlen(trim($partialReply)) < 2) $partialReply = null;
                }
                $resp = [
                    'success' => true,
                    'status'  => $item['status'],  // pending | processing
                ];
                if ($partialReply) {
                    $resp['partial_reply'] = $partialReply;
                }
                echo json_encode($resp);
            }
            break;

        // ─── request_song: User asks Ailey to generate a song from chat lyrics ───
        case 'request_song':
            $user = $auth->requireAuth();
            $lyrics = trim($input['lyrics'] ?? '');
            if (strlen($lyrics) < 40) { echo json_encode(['error' => 'lyrics_too_short']); break; }
            $title  = trim($input['title']  ?? '') ?: 'Untitled';
            $genre  = trim($input['genre']  ?? '');
            $mood   = trim($input['mood']   ?? '');
            $tags   = trim($input['tags']   ?? '');
            $sourceQueueId = trim($input['source_queue_id'] ?? '');
            $duration = (int)($input['duration'] ?? 180);
            if ($duration < 30) $duration = 30;
            if ($duration > 240) $duration = 240;
            $requestId = 'sreq_' . bin2hex(random_bytes(8));
            $reqDir = __DIR__ . '/uploads/song_requests';
            if (!is_dir($reqDir)) mkdir($reqDir, 0755, true);
            $reqPayload = [
                'request_id' => $requestId,
                'user_id'    => $user['id'],
                'user_name'  => $user['display_name'] ?? ($user['username'] ?? 'User'),
                'source_queue_id' => $sourceQueueId,
                'lyrics'     => $lyrics,
                'title'      => $title,
                'genre'      => $genre,
                'mood'       => $mood,
                'tags'       => $tags,
                'duration'   => $duration,
                'status'     => 'pending',
                'progress'   => 'Warteschlange…',
                'created_at' => time(),
                'updated_at' => time(),
            ];
            file_put_contents($reqDir . '/' . $requestId . '.json', json_encode($reqPayload));
            echo json_encode([
                'success'    => true,
                'request_id' => $requestId,
                'status'     => 'pending',
            ]);
            break;

        // ─── check_song_status: User polls song generation progress ───
        case 'check_song_status':
            $user = $auth->requireAuth();
            $reqId = $_GET['request_id'] ?? $input['request_id'] ?? '';
            if (!$reqId) { echo json_encode(['error' => 'request_id required']); break; }
            $safeReq = preg_replace('/[^a-zA-Z0-9_-]/', '', $reqId);
            $reqFile = __DIR__ . '/uploads/song_requests/' . $safeReq . '.json';
            if (!is_file($reqFile)) { echo json_encode(['error' => 'not_found']); break; }
            $data = json_decode(file_get_contents($reqFile), true);
            if (!is_array($data) || ($data['user_id'] ?? '') !== $user['id']) {
                echo json_encode(['error' => 'forbidden']); break;
            }
            echo json_encode([
                'success'    => true,
                'request_id' => $reqId,
                'status'     => $data['status'] ?? 'pending',
                'progress'   => $data['progress'] ?? '',
                'mp3_url'    => $data['mp3_url'] ?? null,
                'cover_url'  => $data['cover_url'] ?? null,
                'title'      => $data['title'] ?? '',
                'error'      => $data['error'] ?? null,
            ]);
            break;

        // ─── poll_song_requests: Ailey Core asks "any pending song jobs?" ───
        case 'poll_song_requests':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $reqDir = __DIR__ . '/uploads/song_requests';
            $out = [];
            if (is_dir($reqDir)) {
                foreach (glob($reqDir . '/*.json') as $f) {
                    // Cleanup finished/failed requests older than 24h
                    if ((time() - filemtime($f)) > 86400) { @unlink($f); continue; }
                    $d = json_decode(file_get_contents($f), true);
                    if (!is_array($d)) continue;
                    if (($d['status'] ?? '') === 'pending') {
                        // Mark as 'queued' so poller doesn't double-pick
                        $d['status'] = 'queued';
                        $d['updated_at'] = time();
                        file_put_contents($f, json_encode($d));
                        $out[] = $d;
                    }
                }
            }
            echo json_encode(['success' => true, 'count' => count($out), 'items' => $out]);
            break;

        // ─── push_song_status: Ailey Core updates song job progress ───
        case 'push_song_status':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $reqId = $input['request_id'] ?? '';
            if (!$reqId) { echo json_encode(['error' => 'request_id required']); break; }
            $safeReq = preg_replace('/[^a-zA-Z0-9_-]/', '', $reqId);
            $reqFile = __DIR__ . '/uploads/song_requests/' . $safeReq . '.json';
            if (!is_file($reqFile)) { echo json_encode(['error' => 'not_found']); break; }
            $data = json_decode(file_get_contents($reqFile), true);
            if (!is_array($data)) { echo json_encode(['error' => 'corrupt']); break; }
            foreach (['status', 'progress', 'mp3_url', 'cover_url', 'title', 'error'] as $k) {
                if (array_key_exists($k, $input)) $data[$k] = $input[$k];
            }
            $data['updated_at'] = time();
            file_put_contents($reqFile, json_encode($data));
            echo json_encode(['success' => true]);
            break;

        // ─── upload_chat_file: Upload image/document before send_message ───
        case 'upload_chat_file':
            $user = $auth->requireAuth();
            if (empty($_FILES['file'])) {
                echo json_encode(['error' => 'No file uploaded']);
                break;
            }
            $origName = basename($_FILES['file']['name']);
            $ext = strtolower(pathinfo($origName, PATHINFO_EXTENSION));
            // Allowed extensions: images + documents
            $allowedImg = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff', 'heic'];
            $allowedDoc = ['txt', 'md', 'json', 'xml', 'csv', 'tsv', 'yaml', 'yml', 'toml',
                           'ini', 'cfg', 'conf', 'log', 'pdf', 'docx',
                           'py', 'js', 'ts', 'jsx', 'tsx', 'html', 'css', 'scss',
                           'java', 'c', 'cpp', 'h', 'hpp', 'rs', 'go', 'rb', 'php',
                           'sh', 'bash', 'zsh', 'sql', 'r', 'swift', 'kt', 'lua',
                           'pl', 'tex', 'bib', 'env', 'dockerfile'];
            $allAllowed = array_merge($allowedImg, $allowedDoc);
            if (!in_array($ext, $allAllowed)) {
                echo json_encode(['error' => 'file_type_not_allowed', 'message' => 'Dateityp nicht erlaubt.']);
                break;
            }
            // Max 20 MB
            if ($_FILES['file']['size'] > 20 * 1024 * 1024) {
                echo json_encode(['error' => 'file_too_large', 'message' => 'Datei zu groß (max 20 MB).']);
                break;
            }
            $fileType = in_array($ext, $allowedImg) ? 'image' : 'document';
            $userId = preg_replace('/[^a-zA-Z0-9_-]/', '', $user['id']);
            $baseDir = __DIR__ . '/uploads/chat_files/' . $userId;
            if (!is_dir($baseDir)) { mkdir($baseDir, 0755, true); }
            // Cleanup: remove files older than 1 hour in this user's dir
            foreach (glob($baseDir . '/*') as $oldFile) {
                if (is_file($oldFile) && (time() - filemtime($oldFile)) > 3600) {
                    @unlink($oldFile);
                }
            }
            // Safe filename with timestamp
            $safeName = preg_replace('/[^a-zA-Z0-9_.-]/', '_', pathinfo($origName, PATHINFO_FILENAME));
            $finalName = $safeName . '_' . time() . '.' . $ext;
            $destPath = $baseDir . '/' . $finalName;
            if (move_uploaded_file($_FILES['file']['tmp_name'], $destPath)) {
                $proto = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
                $host = $_SERVER['HTTP_HOST'] ?? 'hey-ailey.com';
                $relPath = 'uploads/chat_files/' . $userId . '/' . $finalName;
                $url = $proto . '://' . $host . '/' . $relPath;
                echo json_encode([
                    'success'   => true,
                    'url'       => $url,
                    'filename'  => $origName,
                    'file_type' => $fileType,
                ]);
            } else {
                echo json_encode(['error' => 'Upload fehlgeschlagen.']);
            }
            break;

        // ═══════════════════ AILEY CORE ENDPOINTS ═══════════════
        // Ailey Core calls these with X-Portal-Key header

        // ─── poll_pending: Ailey asks "any new messages?" ───────
        case 'poll_pending':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            // Clean up stale 'processing' items (stuck > 10 minutes)
            // Vision/document processing can take 3-5 min (model swap + inference)
            PortalDB::resetStaleQueueItems(600);

            $limit = min((int)($_GET['limit'] ?? 5), 20);
            $items = PortalDB::getPendingQueue($limit);

            // Mark as processing
            foreach ($items as &$item) {
                PortalDB::updateQueueStatus($item['id'], 'processing');
                $item['status'] = 'processing';
            }

            echo json_encode(['success' => true, 'count' => count($items), 'items' => $items]);
            break;

        // ─── push_reply: Ailey sends generated reply ────────────
        case 'push_reply':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $queueId      = $input['queue_id'] ?? '';
            $reply         = $input['reply'] ?? '';
            $mood          = $input['mood'] ?? 'neutral';
            $title         = $input['conversation_title'] ?? null;
            $tokens        = $input['tokens_generated'] ?? null;
            $processingMs  = $input['processing_ms'] ?? null;
            $status        = $input['status'] ?? 'done';
            $suggestions   = !empty($input['suggestions']) ? json_encode($input['suggestions']) : null;
            $imageUrl      = $input['image_url'] ?? null;
            $imageTitle    = $input['image_title'] ?? null;
            $isHamster     = !empty($input['is_hamster']);
            $thinkingContent = $input['thinking'] ?? '';
            $hasInteractive = !empty($input['has_interactive']);
            $songDetected = $input['song_detected'] ?? null; // {is_song,confidence,title,suggested_genre,suggested_mood,suggested_tags,needs_metadata,...}

            if (!$queueId) { echo json_encode(['error' => 'queue_id required']); break; }

            $item = PortalDB::getOfflineItemById($queueId);
            if (!$item) { echo json_encode(['error' => 'not_found']); break; }

            // Store thinking/reasoning content as cache file for frontend retrieval
            if ($thinkingContent && strlen(trim($thinkingContent)) > 5) {
                $thinkDir = __DIR__ . '/uploads/thinking_cache';
                if (!is_dir($thinkDir)) mkdir($thinkDir, 0755, true);
                $safeQid = preg_replace('/[^a-zA-Z0-9_-]/', '', $queueId);
                file_put_contents($thinkDir . '/' . $safeQid . '.txt', $thinkingContent);
            }

            // Store interactive flag as cache file for frontend retrieval
            if ($hasInteractive) {
                $interDir = __DIR__ . '/uploads/interactive_cache';
                if (!is_dir($interDir)) mkdir($interDir, 0755, true);
                $safeQid2 = preg_replace('/[^a-zA-Z0-9_-]/', '', $queueId);
                file_put_contents($interDir . '/' . $safeQid2 . '.flag', '1');
            }

            // Store song_detected JSON as cache file for frontend retrieval
            if (is_array($songDetected) && !empty($songDetected['is_song'])) {
                $songDir = __DIR__ . '/uploads/song_detect';
                if (!is_dir($songDir)) mkdir($songDir, 0755, true);
                $safeQid3 = preg_replace('/[^a-zA-Z0-9_-]/', '', $queueId);
                file_put_contents($songDir . '/' . $safeQid3 . '.json', json_encode($songDetected));
            }

            if ($status === 'done' && $reply) {
                // Tool jobs (image_gen, song_gen) have empty conversation_id — skip message storage
                // Game queue items use conversation_id like "game_xxx" — also skip
                $convId = $item['conversation_id'] ?? '';
                $isToolJob = ($convId === '' || str_starts_with($item['message'] ?? '', '__tool:'));
                $isGameItem = str_starts_with($convId, 'game_') || ($convId === 'game_results');
                if (!$isToolJob && !$isGameItem) {
                    // Store reply as message (with image_url and chat_mode if present)
                    $chatModeForMsg = $isHamster ? 'hamster' : null;
                    $msgId = PortalDB::addMessage($item['conversation_id'], 'assistant', $reply, $mood, $tokens, $processingMs, $imageUrl, $chatModeForMsg, ($thinkingContent !== '' ? $thinkingContent : null));
                    PortalDB::updateConversation($item['conversation_id']);
                    if ($title) {
                        PortalDB::updateConversationTitle($item['conversation_id'], $title);
                    }
                }
                PortalDB::updateQueueItem($queueId, 'done', $reply, $mood, $title, $processingMs, $suggestions, $imageUrl);

                // ── Extract artifacts (only for real conversations) ──────
                if (!$isToolJob && !$isGameItem && !empty($convId) && !empty($msgId)) {
                try {
                    if (preg_match_all('/```(\w*)\n([\s\S]*?)```/', $reply, $matches, PREG_SET_ORDER)) {
                        foreach ($matches as $m) {
                            $lang = strtolower($m[1] ?: '');
                            $code = $m[2];
                            if (strlen(trim($code)) < 10) continue; // skip trivial snippets
                            $isSvg = ($lang === 'svg') || (stripos(trim($code), '<svg') === 0 && strpos($code, '</svg>') !== false);
                            $type = $isSvg ? 'svg' : 'code';
                            // Auto-title from first meaningful line
                            $firstLine = trim(strtok(trim($code), "\n"));
                            $autoTitle = mb_substr($firstLine, 0, 80);
                            if ($isSvg) $autoTitle = 'SVG — ' . ($title ?: date('d.m.Y H:i'));
                            PortalDB::addArtifact($item['user_id'], $item['conversation_id'], $msgId, $type, $lang ?: null, $autoTitle, $code);
                        }
                    }
                    // ── Extract song artifacts (Suno format with [Verse]/[Chorus]) ──
                    if (preg_match('/\[(?:Verse|Chorus|Intro|Bridge|Hook|Outro)\s*\d*\]/i', $reply)) {
                        // Extract the song portion — from Title: or first bracket to end of song structure
                        $songText = $reply;
                        // Try to find Title: line
                        $songTitle = 'Song — ' . date('d.m.Y H:i');
                        if (preg_match('/Title:\s*["\']?(.+?)["\']?\s*$/m', $songText, $tm)) {
                            $songTitle = trim($tm[1], '" ');
                        }
                        // Extract from first [Genre:] or [Verse] to last [Outro]/bracket section
                        if (preg_match('/(\[(?:Genre|Verse|Intro|Chorus)[\s\S]*(?:\[Outro\][\s\S]*?(?:\n\n|\z)|(?:\[Chorus\][\s\S]*?)(?:\n\n\n|\z)))/i', $songText, $sm)) {
                            $songContent = trim($sm[1]);
                        } else {
                            // Fallback: grab everything from first bracket marker
                            $firstBracket = strpos($songText, '[');
                            $songContent = $firstBracket !== false ? trim(substr($songText, $firstBracket)) : trim($songText);
                        }
                        if (strlen($songContent) > 50) {
                            PortalDB::addArtifact($item['user_id'], $item['conversation_id'], $msgId, 'song', null, $songTitle, $songContent);
                        }
                    }
                    // ── Extract image artifact (when image_url is present) ──
                    if ($imageUrl) {
                        $imgTitle = $imageTitle ?: ('🎨 Bild — ' . date('d.m.Y H:i'));
                        PortalDB::addArtifact($item['user_id'], $item['conversation_id'], $msgId, 'image', null, $imgTitle, $imageUrl);
                    }
                } catch (\Exception $e) {
                    error_log("[Portal] artifact extraction error: " . $e->getMessage());
                }
                } // end if (!$isToolJob && !$isGameItem) for artifacts
            } else {
                PortalDB::updateQueueItem($queueId, 'failed', $reply ?: 'Generation failed');
            }

            echo json_encode(['success' => true]);
            break;

        // ─── push_partial: Ailey sends partial reply during generation ──
        case 'push_partial':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $queueId     = $input['queue_id'] ?? '';
            $partialText = $input['partial_reply'] ?? '';
            if (!$queueId) { echo json_encode(['error' => 'queue_id required']); break; }
            // Store partial reply in a lightweight cache file (no DB writes per token)
            $cacheDir = __DIR__ . '/uploads/partial_cache';
            if (!is_dir($cacheDir)) mkdir($cacheDir, 0755, true);
            $cacheFile = $cacheDir . '/' . preg_replace('/[^a-zA-Z0-9_-]/', '', $queueId) . '.txt';
            file_put_contents($cacheFile, $partialText);
            // Also mark item as "processing" if still pending
            $item = PortalDB::getOfflineItemById($queueId);
            if ($item && $item['status'] === 'pending') {
                PortalDB::updateQueueItemStatus($queueId, 'processing');
            }
            echo json_encode(['success' => true]);
            break;

        // ─── cancel_generation: User stops generation mid-stream ──
        case 'cancel_generation':
            $user = $auth->requireAuth();
            $queueId = $input['queue_id'] ?? '';
            if (!$queueId) { echo json_encode(['error' => 'queue_id required']); break; }
            $item = PortalDB::getOfflineItem($queueId, $user['id']);
            if (!$item) { echo json_encode(['error' => 'not_found']); break; }
            if (in_array($item['status'], ['pending', 'processing'])) {
                // Write cancel flag file — poller checks this during streaming
                $cancelDir = __DIR__ . '/uploads/cancel_flags';
                if (!is_dir($cancelDir)) mkdir($cancelDir, 0755, true);
                $safeId = preg_replace('/[^a-zA-Z0-9_-]/', '', $queueId);
                file_put_contents($cancelDir . '/' . $safeId, '1');
                // Get whatever partial text exists
                $partialText = '';
                $partialFile = __DIR__ . '/uploads/partial_cache/' . $safeId . '.txt';
                if (is_file($partialFile)) {
                    $partialText = trim(file_get_contents($partialFile));
                }
                // If we have partial text, save it as the reply (stripped of thinking tags)
                if (strlen($partialText) > 10) {
                    // Strip thinking tags
                    $cleaned = preg_replace('/<(think|thinking|thought)\b[^>]*>.*?(<\/(think|thinking|thought)>)/si', '', $partialText);
                    $cleaned = preg_replace('/<(think|thinking|thought)\b[^>]*>[\s\S]*/i', '', $cleaned);
                    $cleaned = trim($cleaned);
                    if (strlen($cleaned) > 5) {
                        $cleaned .= "\n\n*(Generierung vom Nutzer gestoppt)*";
                        PortalDB::updateQueueItem($queueId, 'done', $cleaned, 'neutral', null, null, null, null);
                    } else {
                        PortalDB::updateQueueStatus($queueId, 'cancelled');
                    }
                } else {
                    PortalDB::updateQueueStatus($queueId, 'cancelled');
                }
                echo json_encode(['success' => true, 'cancelled' => true]);
            } else {
                echo json_encode(['success' => true, 'cancelled' => false, 'reason' => 'already_done']);
            }
            break;

        // ─── check_cancel: Poller checks if user cancelled ──
        case 'check_cancel':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $queueId = $_GET['queue_id'] ?? '';
            if (!$queueId) { echo json_encode(['cancelled' => false]); break; }
            $cancelDir = __DIR__ . '/uploads/cancel_flags';
            $safeId = preg_replace('/[^a-zA-Z0-9_-]/', '', $queueId);
            $flagFile = $cancelDir . '/' . $safeId;
            $cancelled = is_file($flagFile);
            if ($cancelled) @unlink($flagFile); // consume the flag
            echo json_encode(['cancelled' => $cancelled]);
            break;

        // ─── heartbeat: Ailey touches queue item during long processing ──
        case 'heartbeat':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $queueId = $input['queue_id'] ?? '';
            if (!$queueId) { echo json_encode(['error' => 'queue_id required']); break; }
            PortalDB::touchQueueItem($queueId);
            echo json_encode(['success' => true]);
            break;

        // ─── reset_queue_item: Ailey defers item back to pending ─
        case 'reset_queue_item':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $queueId = $input['queue_id'] ?? '';
            if (!$queueId) { echo json_encode(['error' => 'queue_id required']); break; }
            PortalDB::updateQueueStatus($queueId, 'pending');
            echo json_encode(['success' => true]);
            break;

        // ─── push_summary: Ailey sends conversation summary ────
        case 'push_summary':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $convId = $input['conversation_id'] ?? '';
            $summary = $input['summary'] ?? '';
            if ($convId && $summary) {
                PortalDB::updateConversationSummary($convId, $summary);
            }
            echo json_encode(['success' => true]);
            break;

        // ─── push_memories: Ailey Core pushes extracted user memories ──
        case 'push_memories':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $userId = $input['user_id'] ?? '';
            $memories = $input['memories'] ?? [];
            $convId = $input['conversation_id'] ?? null;
            if ($userId && is_array($memories) && count($memories) > 0) {
                $stored = PortalDB::storeMemories($userId, $memories, $convId);
                echo json_encode(['success' => true, 'stored' => $stored]);
            } else {
                echo json_encode(['success' => true, 'stored' => 0]);
            }
            break;

        // ─── get_user_memories: Ailey Core fetches memories for context building ──
        case 'get_user_memories':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $userId = $input['user_id'] ?? $_GET['user_id'] ?? '';
            $limit = (int)($input['limit'] ?? $_GET['limit'] ?? 20);
            if ($userId) {
                $memories = PortalDB::getUserMemories($userId, min($limit, 50));
                echo json_encode(['success' => true, 'memories' => $memories]);
            } else {
                echo json_encode(['error' => 'user_id required']);
            }
            break;

        // ─── touch_memories: Ailey Core reports which memories were used ──
        case 'touch_memories':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $userId = $input['user_id'] ?? '';
            $memoryIds = $input['memory_ids'] ?? [];
            if ($userId && is_array($memoryIds) && count($memoryIds) > 0) {
                PortalDB::touchMemories($userId, $memoryIds);
            }
            echo json_encode(['success' => true]);
            break;

        // ─── decay_memories: Periodic confidence decay (called by cron or poller) ──
        case 'decay_memories':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $userId = $input['user_id'] ?? '';
            $factor = (float)($input['factor'] ?? 0.9);
            if ($userId) {
                PortalDB::decayMemories($userId, $factor);
            }
            echo json_encode(['success' => true]);
            break;

        // ─── update_ailey_status: Ailey pushes online/sleeping status + mood ──
        case 'update_ailey_status':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $status = $input['status'] ?? 'online';  // online | sleeping | offline
            PortalDB::setAileyStatus($status);
            // Also store current mood if provided
            if (!empty($input['mood'])) {
                PortalDB::setAileyMood($input['mood']);
            }
            echo json_encode(['success' => true, 'status' => $status]);
            break;

        // ─── get_ailey_status: Public — portal JS checks this ──
        case 'get_ailey_status':
            $status = PortalDB::getAileyStatus();
            $mood   = PortalDB::getAileyMood();
            echo json_encode(['success' => true, 'status' => $status, 'mood' => $mood]);
            break;

        // ─── push_public_content: Ailey Core pushes content snapshot ──
        case 'push_public_content':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $content = $input;
            if (!$content || !is_array($content)) {
                echo json_encode(['error' => 'invalid content']);
                break;
            }
            PortalDB::setPublicContent($content);
            echo json_encode(['success' => true]);
            break;

        // ─── get_public_content: Public — landing page data ──
        case 'get_public_content':
            $content = PortalDB::getPublicContent();
            $status  = PortalDB::getAileyStatus();
            $mood    = PortalDB::getAileyMood();
            echo json_encode([
                'success' => true,
                'status'  => $status,
                'mood'    => $mood,
                'content' => $content ?: new \stdClass(),
            ]);
            break;

        // ═══════════════════ BAN / WARNING CHECK ═══════════════════
        case 'check_ban':
            $user = $auth->requireAuth();
            $info = PortalDB::getWarningInfo($user['id']);
            echo json_encode(['success' => true, 'warning' => $info]);
            break;

        // ═══════════════════ PREFERENCES ═══════════════════════════
        case 'get_preferences':
            $user = $auth->requireAuth();
            $prefs = PortalDB::getUserPreferences($user['id']);
            echo json_encode(['success' => true, 'preferences' => $prefs ?: new \stdClass()]);
            break;

        case 'save_preferences':
            $user = $auth->requireAuth();
            $prefs = [
                'about_me'       => $input['about_me'] ?? '',
                'response_style' => $input['response_style'] ?? '',
                'other'          => $input['other'] ?? '',
            ];
            PortalDB::saveUserPreferences($user['id'], $prefs);
            echo json_encode(['success' => true]);
            break;

        // ═══════════════════ DSGVO ══════════════════════════════
        case 'delete_my_data':
            $user = $auth->requireAuth();
            $deleted = PortalDB::deleteUserData($user['id']);
            // Queue deletion on Ailey side
            PortalDB::addSystemQueueItem('delete_user', $user['id'], json_encode([
                'user_id' => $user['id'], 'user_name' => $user['display_name'],
            ]));
            PortalDB::logAdmin('dsgvo_delete', null, $user['id'], json_encode($deleted), $ip);
            $auth->logout();
            echo json_encode(['success' => true, 'deleted' => $deleted]);
            break;

        // ═══════════════════ ADMIN ══════════════════════════════
        case 'admin_stats':
            $auth->requireAdmin();
            echo json_encode(['success' => true, 'stats' => PortalDB::getStats()]);
            break;
        case 'admin_users':
            $auth->requireAdmin();
            echo json_encode(['success' => true, 'users' => PortalDB::listUsers()]);
            break;
        case 'admin_whitelist_add':
            // Allow both: admin session auth OR portal_key auth (from Ailey Core)
            $adminId = null;
            if (verifyPortalKey($config)) {
                $adminId = '__ailey_core__';
            } else {
                $admin = $auth->requireAdmin();
                $adminId = $admin['id'];
            }
            $email = strtolower(trim($input['email'] ?? ''));
            if (!$email || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
                echo json_encode(['error' => 'valid email required']); break;
            }
            $code = PortalDB::addToWhitelist($email, $adminId);
            PortalDB::logAdmin('whitelist_add', $adminId, null, "Email: $email", $ip);
            echo json_encode(['success' => true, 'invite_code' => $code]);
            break;
        case 'admin_suspend_user':
            $admin = $auth->requireAdmin();
            $targetId = $input['user_id'] ?? '';
            $newStatus = $input['status'] ?? 'suspended';
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            if (!in_array($newStatus, ['active', 'suspended'], true)) {
                echo json_encode(['error' => 'invalid status']); break;
            }
            PortalDB::get()->prepare('UPDATE portal_users SET status = ? WHERE id = ?')->execute([$newStatus, $targetId]);
            PortalDB::logAdmin('user_status_change', $admin['id'], $targetId, "Status: $newStatus", $ip);
            echo json_encode(['success' => true]);
            break;

        // ─── Admin: Limits ──────────────────────────────────────
        case 'admin_get_limits':
            $auth->requireAdmin();
            $limits = PortalDB::getEffectiveLimits($config['limits'] ?? []);
            echo json_encode(['success' => true, 'limits' => $limits]);
            break;
        case 'admin_set_limits':
            $admin = $auth->requireAdmin();
            $allowed = ['max_message_length', 'max_hourly', 'max_daily'];
            $changed = [];
            foreach ($allowed as $key) {
                if (isset($input[$key])) {
                    $val = intval($input[$key]);
                    // Sanity bounds
                    if ($key === 'max_message_length') $val = max(100, min(10000, $val));
                    if ($key === 'max_hourly')          $val = max(1, min(200, $val));
                    if ($key === 'max_daily')            $val = max(1, min(1000, $val));
                    PortalDB::setSetting('limit_' . $key, (string)$val);
                    $changed[$key] = $val;
                }
            }
            PortalDB::logAdmin('limits_changed', $admin['id'], null, json_encode($changed), $ip);
            echo json_encode(['success' => true, 'limits' => PortalDB::getEffectiveLimits($config['limits'] ?? [])]);
            break;

        // ─── Admin: Intro Song Setting ──────────────────────────
        case 'admin_get_intro_song':
            $auth->requireAdmin();
            $val = PortalDB::getSetting('intro_song', 'auto');
            echo json_encode(['success' => true, 'intro_song' => $val]);
            break;

        case 'admin_set_intro_song':
            $admin = $auth->requireAdmin();
            $val = trim($input['intro_song'] ?? 'auto');
            // Validate: "auto", "random", or a numeric gallery item ID
            if ($val !== 'auto' && $val !== 'random' && !ctype_digit($val)) {
                echo json_encode(['error' => 'invalid value: auto, random, or gallery item ID']);
                break;
            }
            PortalDB::setSetting('intro_song', $val);
            PortalDB::logAdmin('intro_song_changed', $admin['id'], null, $val, $ip);
            echo json_encode(['success' => true, 'intro_song' => $val]);
            break;

        // ─── Admin Dev-Link: Core → Portal (IP heartbeat) ────────
        // Ailey Core POSTs current LAN + Public IP. Auth via portal_key.
        case 'core_report_devlink':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $lanIp     = trim((string)($input['lan_ip']      ?? ''));
            $publicIp  = trim((string)($input['public_ip']   ?? ''));
            $publicIp6 = trim((string)($input['public_ipv6'] ?? ''));
            $port      = intval($input['port'] ?? ($config['admin_devlink']['port'] ?? 5502));
            $path      = (string)($input['path'] ?? '/app/');
            if (!preg_match('#^/[\w\-/.]*$#', $path)) $path = '/app/';
            // Basic validation — allow IPv4, IPv6, or hostname
            $isValidHost = function($h) {
                if (!$h) return false;
                if (filter_var($h, FILTER_VALIDATE_IP)) return true;
                return (bool)preg_match('/^[a-zA-Z0-9\.\-]{2,253}$/', $h);
            };
            $isValidIPv6 = function($h) {
                return $h && filter_var($h, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6);
            };
            if (!$isValidHost($lanIp) && !$isValidHost($publicIp) && !$isValidIPv6($publicIp6)) {
                echo json_encode(['error' => 'need lan_ip, public_ip or public_ipv6']);
                break;
            }
            if ($port < 1 || $port > 65535) $port = 5502;
            // IPv6 literals must be wrapped in brackets in URLs
            $ipv6Url = $isValidIPv6($publicIp6) ? ('http://[' . $publicIp6 . ']:' . $port . $path) : '';
            $payload = [
                'lan_url'         => $isValidHost($lanIp)    ? ('http://'  . $lanIp    . ':' . $port . $path) : '',
                'public_url'      => $isValidHost($publicIp) ? ('http://'  . $publicIp . ':' . $port . $path) : '',
                'public_ipv6_url' => $ipv6Url,
                'lan_ip'          => $lanIp,
                'public_ip'       => $publicIp,
                'public_ipv6'     => $publicIp6,
                'port'            => $port,
                'path'            => $path,
                'updated_at'      => date('c'),
            ];
            $path = __DIR__ . '/admin_devlink.json';
            @file_put_contents($path, json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT));
            echo json_encode(['success' => true, 'updated_at' => $payload['updated_at']]);
            break;

        // ─── Admin Dev-Link: Admin UI → fetch URLs (password-gated) ──
        case 'admin_get_devlink':
            $admin = $auth->requireAdmin();
            $pw = (string)($input['password'] ?? '');
            $expected = (string)($config['admin_devlink']['password'] ?? '');
            if (!$expected || $expected === 'CHANGE_ME_LOCAL_ONLY') {
                echo json_encode(['error' => 'devlink password not configured in config.php']);
                break;
            }
            if (!hash_equals($expected, $pw)) {
                // Rate-limit brute force via admin log
                PortalDB::logAdmin('devlink_pw_fail', $admin['id'], null, '', $ip);
                usleep(500000); // 0.5s delay
                http_response_code(401);
                echo json_encode(['error' => 'wrong password']);
                break;
            }
            $path = __DIR__ . '/admin_devlink.json';
            $data = is_file($path) ? json_decode((string)@file_get_contents($path), true) : null;
            if (!is_array($data)) {
                echo json_encode([
                    'success' => true,
                    'urls'    => ['lan_url' => '', 'public_url' => '', 'public_ipv6_url' => ''],
                    'note'    => 'No heartbeat received yet — start Ailey Core with portal poller enabled.',
                ]);
                break;
            }
            PortalDB::logAdmin('devlink_pw_ok', $admin['id'], null, '', $ip);
            echo json_encode([
                'success'    => true,
                'urls'       => [
                    'lan_url'         => $data['lan_url']         ?? '',
                    'public_url'      => $data['public_url']      ?? '',
                    'public_ipv6_url' => $data['public_ipv6_url'] ?? '',
                ],
                'updated_at' => $data['updated_at'] ?? null,
            ]);
            break;

        // ─── Public: Get intro song URL (for intro page) ───────
        case 'get_intro_song':
            $setting = PortalDB::getSetting('intro_song', 'auto');
            $songItem = null;

            if ($setting === 'auto') {
                // Newest song with audio
                $items = PortalDB::getGalleryItems('song', 20, 0);
                foreach ($items as $it) {
                    $m = $it['metadata'] ?? [];
                    $url = $m['audio_url'] ?? null;
                    if (!$url && isset($it['file_url']) && preg_match('/\.mp3$/i', $it['file_url'])) $url = $it['file_url'];
                    if ($url) { $songItem = $it; break; }
                }
            } elseif ($setting === 'random') {
                // Random song with audio
                $items = PortalDB::getGalleryItems('song', 100, 0);
                $withAudio = [];
                foreach ($items as $it) {
                    $m = $it['metadata'] ?? [];
                    $url = $m['audio_url'] ?? null;
                    if (!$url && isset($it['file_url']) && preg_match('/\.mp3$/i', $it['file_url'])) $url = $it['file_url'];
                    if ($url) $withAudio[] = $it;
                }
                if ($withAudio) $songItem = $withAudio[array_rand($withAudio)];
            } else {
                // Specific gallery item ID
                $stmt = PortalDB::get()->prepare('SELECT * FROM ailey_gallery_items WHERE id = ? AND published = 1 LIMIT 1');
                $stmt->execute([(int)$setting]);
                $row = $stmt->fetch(\PDO::FETCH_ASSOC);
                if ($row) {
                    $row['metadata'] = json_decode($row['metadata_json'] ?? '{}', true) ?: [];
                    $songItem = $row;
                }
            }

            if ($songItem) {
                $m = $songItem['metadata'] ?? [];
                $audioUrl = $m['audio_url'] ?? ($songItem['file_url'] ?? null);
                echo json_encode([
                    'success' => true,
                    'audio_url' => $audioUrl,
                    'title' => $songItem['title'] ?? '',
                    'id' => $songItem['id'] ?? null,
                ]);
            } else {
                echo json_encode(['success' => false, 'error' => 'no song found']);
            }
            break;

        // ─── Public: get_limits (for chat textarea maxlength) ───
        case 'get_limits':
            $limits = PortalDB::getEffectiveLimits($config['limits'] ?? []);
            echo json_encode(['success' => true, 'limits' => ['max_message_length' => $limits['max_message_length']]]);
            break;

        // ─── Admin: Image Quota Management (LEGACY — kept for compat) ──
        case 'admin_set_image_quota':
            $admin = $auth->requireAdmin();
            $targetId = $input['user_id'] ?? '';
            $quota = intval($input['quota'] ?? 0);
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            $quota = max(0, min(100, $quota));  // cap at 100/day
            PortalDB::setImageQuota($targetId, $quota);
            PortalDB::logAdmin('image_quota_changed', $admin['id'], $targetId, "Quota: $quota/day", $ip);
            echo json_encode(['success' => true, 'quota' => $quota]);
            break;

        // ─── Image quota check (Ailey Core calls this before generating) ──
        case 'check_image_quota':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $targetId = $input['user_id'] ?? $_GET['user_id'] ?? '';
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            $quota = PortalDB::getImageQuota($targetId);
            $user = PortalDB::getUserById($targetId);
            $isAdmin = $user && $user['role'] === 'admin';
            echo json_encode(['success' => true, 'quota' => $quota, 'is_admin' => $isAdmin]);
            break;

        // ─── Consume image quota (Ailey Core calls after successful generation) ──
        case 'consume_image_quota':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $targetId = $input['user_id'] ?? '';
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            $allowed = PortalDB::consumeImageQuota($targetId);
            echo json_encode(['success' => true, 'allowed' => $allowed]);
            break;

        // ─── User: Get own image quota (for UI feedback) ────────
        case 'my_image_quota':
            $user = $auth->requireAuth();
            $quota = PortalDB::getImageQuota($user['id']);
            echo json_encode(['success' => true, 'quota' => $quota]);
            break;

        // ─── Admin: Song Quota Management ───────────────────────
        case 'admin_set_song_quota':
            $admin = $auth->requireAdmin();
            $targetId = $input['user_id'] ?? '';
            $quota = intval($input['quota'] ?? 0);
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            $quota = max(0, min(50, $quota));
            PortalDB::setSongQuota($targetId, $quota);
            PortalDB::logAdmin('song_quota_changed', $admin['id'], $targetId, "Quota: $quota/day", $ip);
            echo json_encode(['success' => true, 'quota' => $quota]);
            break;

        // ─── Song quota check (Ailey Core calls before generating) ──
        case 'check_song_quota':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $targetId = $input['user_id'] ?? $_GET['user_id'] ?? '';
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            $quota = PortalDB::getSongQuota($targetId);
            $user = PortalDB::getUserById($targetId);
            $isAdmin = $user && $user['role'] === 'admin';
            echo json_encode(['success' => true, 'quota' => $quota, 'is_admin' => $isAdmin]);
            break;

        // ─── Consume song quota (after successful generation) ───
        case 'consume_song_quota':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $targetId = $input['user_id'] ?? '';
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            $allowed = PortalDB::consumeSongQuota($targetId);
            echo json_encode(['success' => true, 'allowed' => $allowed]);
            break;

        // ─── User: Get own song quota (for UI feedback) ─────────
        case 'my_song_quota':
            $user = $auth->requireAuth();
            $quota = PortalDB::getSongQuota($user['id']);
            echo json_encode(['success' => true, 'quota' => $quota]);
            break;

        // ═══════════════════════════════════════════════════════════
        // ═══ V$ (VyrusDollars) Economy Endpoints ═══════════════
        // ═══════════════════════════════════════════════════════════

        // ─── User: Get own V$ balance and info ──────────────────
        case 'vdollars_balance':
            $user = $auth->requireAuth();
            $info = PortalDB::getVdollarsInfo($user['id']);
            echo json_encode(['success' => true, 'vdollars' => $info]);
            break;

        // ─── User: Get V$ transaction history ───────────────────
        case 'vdollars_history':
            $user = $auth->requireAuth();
            $limit = max(5, min(100, intval($_GET['limit'] ?? 20)));
            $history = PortalDB::getVdollarsHistory($user['id'], $limit);
            echo json_encode(['success' => true, 'history' => $history]);
            break;

        // ─── Admin: Set V$ weekly allowance for a user ──────────
        case 'admin_set_vdollars_allowance':
            $admin = $auth->requireAdmin();
            $targetId = $input['user_id'] ?? '';
            $allowance = intval($input['allowance'] ?? 100);
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            $allowance = max(0, min(9999, $allowance));
            PortalDB::setVdollarsAllowance($targetId, $allowance);
            PortalDB::logAdmin('vdollars_allowance_changed', $admin['id'], $targetId, "Allowance: {$allowance} V$/week", $ip);
            echo json_encode(['success' => true, 'allowance' => $allowance]);
            break;

        // ─── Admin: Set V$ balance directly ─────────────────────
        case 'admin_set_vdollars_balance':
            $admin = $auth->requireAdmin();
            $targetId = $input['user_id'] ?? '';
            $balance = floatval($input['balance'] ?? 0);
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            $balance = max(0, min(99999, $balance));
            PortalDB::setVdollarsBalance($targetId, $balance);
            PortalDB::logAdmin('vdollars_balance_set', $admin['id'], $targetId, "Balance set to {$balance} V$", $ip);
            echo json_encode(['success' => true, 'balance' => $balance]);
            break;

        // ─── Backend: Check V$ (Ailey Core calls before generating) ──
        case 'check_vdollars':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $targetId = $input['user_id'] ?? $_GET['user_id'] ?? '';
            $cost = floatval($input['cost'] ?? $_GET['cost'] ?? 0);
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            $info = PortalDB::getVdollarsInfo($targetId);
            echo json_encode([
                'success' => true,
                'balance' => $info['balance'],
                'weekly_allowance' => $info['weekly_allowance'],
                'is_admin' => $info['is_admin'],
                'can_afford' => $info['is_admin'] || $info['balance'] >= $cost,
            ]);
            break;

        // ─── Backend: Spend V$ (Ailey Core calls after successful generation) ──
        case 'spend_vdollars':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $targetId = $input['user_id'] ?? '';
            $amount = floatval($input['amount'] ?? 0);
            $reason = $input['reason'] ?? 'generation';
            if (!$targetId || $amount <= 0) { echo json_encode(['error' => 'user_id and amount required']); break; }
            $allowed = PortalDB::spendVdollars($targetId, $amount, $reason);
            $info = PortalDB::getVdollarsInfo($targetId);
            echo json_encode(['success' => true, 'allowed' => $allowed, 'balance' => $info['balance']]);
            break;

        // ─── Gallery: Rate an item ──────────────────────────────
        case 'gallery_rate':
            $user = $auth->requireAuth();
            $itemId = $input['item_id'] ?? '';
            $rating = intval($input['rating'] ?? 0);
            if (!$itemId || $rating < 1 || $rating > 5) {
                echo json_encode(['error' => 'item_id and rating (1-5) required']);
                break;
            }
            $earned = PortalDB::rateGalleryItem($user['id'], $itemId, $rating);
            $ratingInfo = PortalDB::getGalleryItemRatings($itemId);
            $vInfo = PortalDB::getVdollarsInfo($user['id']);
            echo json_encode([
                'success' => true,
                'earned' => $earned,
                'balance' => $vInfo['balance'],
                'item_rating' => $ratingInfo,
            ]);
            break;

        // ─── Gallery: Comment on an item ────────────────────────
        case 'gallery_comment':
            $user = $auth->requireAuth();
            $itemId = $input['item_id'] ?? '';
            $comment = trim($input['comment'] ?? '');
            if (!$itemId || !$comment) {
                echo json_encode(['error' => 'item_id and comment required']);
                break;
            }
            $result = PortalDB::addGalleryComment($user['id'], $itemId, $comment);
            if (!$result['ok']) {
                echo json_encode(['error' => $result['error']]);
                break;
            }
            $vInfo = PortalDB::getVdollarsInfo($user['id']);
            echo json_encode([
                'success' => true,
                'earned' => $result['earned'],
                'balance' => $vInfo['balance'],
            ]);
            break;

        // ─── Gallery: Get ratings + comments for an item ────────
        case 'gallery_item_interactions':
            $itemId = $_GET['item_id'] ?? '';
            if (!$itemId) { echo json_encode(['error' => 'item_id required']); break; }
            $ratings = PortalDB::getGalleryItemRatings($itemId);
            $comments = PortalDB::getGalleryItemComments($itemId);
            // If user is logged in, include their own rating
            $userRating = null;
            try {
                $user = $auth->requireAuth();
                $userRating = PortalDB::getUserGalleryRating($user['id'], $itemId);
            } catch (\Exception $e) { /* not logged in — fine */ }
            echo json_encode([
                'success' => true,
                'ratings' => $ratings,
                'comments' => $comments,
                'user_rating' => $userRating,
            ]);
            break;

        // ═══════════════════ FORUM ═══════════════════════════════
        case 'forum_topics':
            $category = $_GET['category'] ?? '';
            $page = max(1, intval($_GET['page'] ?? 1));
            $limit = 20;
            $offset = ($page - 1) * $limit;
            $topics = PortalDB::getForumTopics($category, $limit, $offset);
            $total = PortalDB::getForumTopicCount($category);
            echo json_encode(['success' => true, 'topics' => $topics, 'total' => $total, 'page' => $page]);
            break;

        case 'forum_topic':
            $topicId = $_GET['topic_id'] ?? '';
            if (!$topicId) { echo json_encode(['error' => 'topic_id required']); break; }
            $topic = PortalDB::getForumTopic($topicId);
            if (!$topic) { echo json_encode(['error' => 'not_found']); break; }
            $replies = PortalDB::getForumReplies($topicId);
            // Gather like status for logged-in user
            $userLikes = [];
            try {
                $user = $auth->requireAuth();
                $allIds = array_merge([$topicId], array_column($replies, 'id'));
                $userLikes = PortalDB::getUserForumLikes($user['id'], $allIds);
            } catch (\Exception $e) { /* not logged in */ }
            echo json_encode(['success' => true, 'topic' => $topic, 'replies' => $replies, 'user_likes' => $userLikes]);
            break;

        case 'forum_create_topic':
            $user = $auth->requireAuth();
            $category = $input['category'] ?? 'general';
            $title = trim($input['title'] ?? '');
            $body = trim($input['body'] ?? '');
            $validCategories = ['general', 'feedback', 'kreativ', 'technik', 'offtopic'];
            if (!in_array($category, $validCategories, true)) $category = 'general';
            if (strlen($title) < 3) { echo json_encode(['error' => 'Titel muss mindestens 3 Zeichen haben.']); break; }
            if (strlen($body) < 5) { echo json_encode(['error' => 'Beitrag muss mindestens 5 Zeichen haben.']); break; }
            $topicId = PortalDB::createForumTopic($user['id'], $user['display_name'], $category, $title, $body);
            echo json_encode(['success' => true, 'topic_id' => $topicId]);
            break;

        case 'forum_create_reply':
            $user = $auth->requireAuth();
            $topicId = $input['topic_id'] ?? '';
            $body = trim($input['body'] ?? '');
            if (!$topicId) { echo json_encode(['error' => 'topic_id required']); break; }
            if (strlen($body) < 2) { echo json_encode(['error' => 'Antwort muss mindestens 2 Zeichen haben.']); break; }
            $topic = PortalDB::getForumTopic($topicId);
            if (!$topic) { echo json_encode(['error' => 'not_found']); break; }
            if ($topic['is_locked']) { echo json_encode(['error' => 'Dieses Thema ist gesperrt.']); break; }
            $replyId = PortalDB::createForumReply($topicId, $user['id'], $user['display_name'], $body);
            echo json_encode(['success' => true, 'reply_id' => $replyId]);
            break;

        case 'forum_like':
            // Allow logged-in users to like topics/replies
            $user = $auth->requireAuth();
            $targetType = $input['target_type'] ?? '';
            $targetId = $input['target_id'] ?? '';
            if (!in_array($targetType, ['topic', 'reply'], true) || !$targetId) {
                echo json_encode(['error' => 'target_type (topic/reply) and target_id required']);
                break;
            }
            $result = PortalDB::toggleForumLike($user['id'], $targetType, $targetId);
            echo json_encode(['success' => true, 'liked' => $result['liked']]);
            break;

        case 'forum_unreplied':
            // For Ailey Core bot: get topics without Ailey reply
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $hours = intval($_GET['hours'] ?? 2);
            $topics = PortalDB::getUnrepliedForumTopics($hours);
            echo json_encode(['success' => true, 'topics' => $topics]);
            break;

        case 'forum_ailey_reply':
            // For Ailey Core bot: post Ailey's reply to a topic
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $topicId = $input['topic_id'] ?? '';
            $body = trim($input['body'] ?? '');
            if (!$topicId || !$body) { echo json_encode(['error' => 'topic_id and body required']); break; }
            // Use a fixed Ailey user ID or "system"
            $replyId = PortalDB::createForumReply($topicId, 'ailey-system', 'Ailey 💜', $body, true);
            echo json_encode(['success' => true, 'reply_id' => $replyId]);
            break;

        // ─── Admin: Send V$ to user ─────────────────────────────
        case 'admin_send_vdollars':
            $admin = $auth->requireAdmin();
            $targetId = $input['user_id'] ?? '';
            $amount = floatval($input['amount'] ?? 0);
            $reason = trim($input['reason'] ?? 'Admin-Geschenk');
            if (!$targetId || $amount <= 0 || $amount > 1000) {
                echo json_encode(['error' => 'user_id and amount (1-1000) required']);
                break;
            }
            PortalDB::earnVdollars($targetId, $amount, "admin_gift:{$reason}");
            PortalDB::logAdmin('vdollars_gift', $admin['id'], $targetId, "Sent {$amount} V$ — {$reason}", $ip);
            $vInfo = PortalDB::getVdollarsInfo($targetId);
            echo json_encode(['success' => true, 'balance' => $vInfo['balance']]);
            break;

        // ─── Admin: Upgrade user tier ───────────────────────────
        case 'admin_set_user_tier':
            $admin = $auth->requireAdmin();
            $targetId = $input['user_id'] ?? '';
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            PortalDB::upgradeUserTier($targetId);
            PortalDB::logAdmin('tier_upgraded', $admin['id'], $targetId, 'public → invited', $ip);
            echo json_encode(['success' => true]);
            break;

        // ─── Profile: Upload Avatar ─────────────────────────────
        case 'upload_avatar':
            $user = $auth->requireAuth();
            if (!isset($_FILES['avatar']) || $_FILES['avatar']['error'] !== UPLOAD_ERR_OK) {
                echo json_encode(['error' => 'No avatar file uploaded']);
                break;
            }
            $file = $_FILES['avatar'];
            $maxSize = 5 * 1024 * 1024; // 5 MB
            if ($file['size'] > $maxSize) {
                echo json_encode(['error' => 'File too large (max 5MB)']);
                break;
            }
            $mime = mime_content_type($file['tmp_name']);
            if (!in_array($mime, ['image/jpeg', 'image/png', 'image/webp', 'image/gif'], true)) {
                echo json_encode(['error' => 'Invalid image type']);
                break;
            }
            // Resize to max 200x200 to save space
            $img = null;
            switch ($mime) {
                case 'image/jpeg': $img = @imagecreatefromjpeg($file['tmp_name']); break;
                case 'image/png':  $img = @imagecreatefrompng($file['tmp_name']); break;
                case 'image/webp': $img = @imagecreatefromwebp($file['tmp_name']); break;
                case 'image/gif':  $img = @imagecreatefromgif($file['tmp_name']); break;
            }
            if (!$img) {
                echo json_encode(['error' => 'Could not process image']);
                break;
            }
            $origW = imagesx($img);
            $origH = imagesy($img);
            $targetSize = 200;
            // Crop to square (center crop), then resize
            $cropSize = min($origW, $origH);
            $cropX = (int)(($origW - $cropSize) / 2);
            $cropY = (int)(($origH - $cropSize) / 2);
            $thumb = imagecreatetruecolor($targetSize, $targetSize);
            // Preserve transparency for PNG
            imagealphablending($thumb, false);
            imagesavealpha($thumb, true);
            imagecopyresampled($thumb, $img, 0, 0, $cropX, $cropY, $targetSize, $targetSize, $cropSize, $cropSize);
            // Save as WebP for best compression
            $avatarDir = __DIR__ . '/uploads/avatars';
            if (!is_dir($avatarDir)) mkdir($avatarDir, 0755, true);
            $filename = $user['id'] . '_' . time() . '.webp';
            $filepath = $avatarDir . '/' . $filename;
            imagewebp($thumb, $filepath, 85);
            imagedestroy($img);
            imagedestroy($thumb);
            // Delete old avatar if exists
            $oldProfile = PortalDB::getProfile($user['id']);
            if ($oldProfile && $oldProfile['avatar_url']) {
                $oldFile = __DIR__ . $oldProfile['avatar_url'];
                if (file_exists($oldFile)) @unlink($oldFile);
            }
            $avatarUrl = '/uploads/avatars/' . $filename;
            PortalDB::updateProfile($user['id'], ['avatar_url' => $avatarUrl]);
            // Check profile_complete achievement
            $newBadges = PortalDB::checkAndUnlockAchievements($user['id']);
            echo json_encode(['success' => true, 'avatar_url' => $avatarUrl, 'new_badges' => $newBadges]);
            break;

        // ─── Profile: Update Bio / Display Name / Equipped Badge ─
        case 'update_profile':
            $user = $auth->requireAuth();
            $updates = [];
            if (isset($input['bio'])) $updates['bio'] = $input['bio'];
            if (isset($input['display_name'])) $updates['display_name'] = $input['display_name'];
            if (array_key_exists('equipped_badge', $input)) $updates['equipped_badge'] = $input['equipped_badge'];
            if (empty($updates)) { echo json_encode(['error' => 'No fields to update']); break; }
            PortalDB::updateProfile($user['id'], $updates);
            // Check profile_complete achievement
            $newBadges = PortalDB::checkAndUnlockAchievements($user['id']);
            echo json_encode(['success' => true, 'new_badges' => $newBadges]);
            break;

        // ─── Profile: Get own profile ────────────────────────────
        case 'get_profile':
            $user = $auth->requireAuth();
            $profile = PortalDB::getProfile($user['id']);
            $badges = PortalDB::getUserBadges($user['id']);
            $allBadges = PortalDB::getBadgeDefinitions();
            echo json_encode(['success' => true, 'profile' => $profile, 'badges' => $badges, 'all_badges' => $allBadges]);
            break;

        // ─── Badges: Get my badges ──────────────────────────────
        case 'get_badges':
            $user = $auth->requireAuth();
            $badges = PortalDB::getUserBadges($user['id']);
            echo json_encode(['success' => true, 'badges' => $badges]);
            break;

        // ─── Badges: Equip badge ────────────────────────────────
        case 'equip_badge':
            $user = $auth->requireAuth();
            $badgeId = $input['badge_id'] ?? null; // null to unequip
            PortalDB::equipBadge($user['id'], $badgeId);
            echo json_encode(['success' => true]);
            break;

        // ─── Badges: Check achievements (trigger check) ─────────
        case 'check_achievements':
            $user = $auth->requireAuth();
            $newBadges = PortalDB::checkAndUnlockAchievements($user['id']);
            echo json_encode(['success' => true, 'new_badges' => $newBadges]);
            break;

        // ─── Chat: Rate a message (training data) ───────────────
        case 'rate_message':
            $user = $auth->requireAuth();
            $messageId = $input['message_id'] ?? '';
            $conversationId = $input['conversation_id'] ?? '';
            $rating = (int)($input['rating'] ?? 0);
            $comment = isset($input['comment']) ? mb_substr(trim($input['comment']), 0, 500) : null;
            if (!$messageId || !$conversationId || !in_array($rating, [-1, 1], true)) {
                echo json_encode(['error' => 'message_id, conversation_id, and rating (1 or -1) required']);
                break;
            }
            $result = PortalDB::rateChatMessage($user['id'], $messageId, $conversationId, $rating, $comment);
            // Earn 0.5 V$ for giving feedback
            PortalDB::earnVdollars($user['id'], 0.5, 'chat_rating');
            // Check achievements
            $newBadges = PortalDB::checkAndUnlockAchievements($user['id']);
            $result['new_badges'] = $newBadges;
            echo json_encode($result);
            break;

        // ─── Chat: Get ratings for conversation ─────────────────
        case 'get_message_ratings':
            $user = $auth->requireAuth();
            $conversationId = $input['conversation_id'] ?? ($_GET['conversation_id'] ?? '');
            if (!$conversationId) { echo json_encode(['error' => 'conversation_id required']); break; }
            $ratings = PortalDB::getChatRatingsForConversation($user['id'], $conversationId);
            echo json_encode(['success' => true, 'ratings' => $ratings]);
            break;

        // ─── Admin: Export chat training data ────────────────────
        case 'export_training_data':
            $admin = $auth->requireAdmin();
            $limit = min(1000, max(1, (int)($input['limit'] ?? $_GET['limit'] ?? 500)));
            $offset = max(0, (int)($input['offset'] ?? $_GET['offset'] ?? 0));
            $data = PortalDB::exportChatRatingsForTraining($limit, $offset);
            echo json_encode(['success' => true, 'count' => count($data), 'data' => $data]);
            break;

        // ─── Admin: Tool Access Toggle ──────────────────────────
        case 'admin_set_tool_access':
            $admin = $auth->requireAdmin();
            $targetId = $input['user_id'] ?? '';
            $tool = $input['tool'] ?? '';
            $enabled = (bool)($input['enabled'] ?? false);
            if (!$targetId || !in_array($tool, ['image_gen', 'song_gen'], true)) {
                echo json_encode(['error' => 'user_id and valid tool required']);
                break;
            }
            PortalDB::setToolAccess($targetId, $tool, $enabled);
            PortalDB::logAdmin('tool_access_changed', $admin['id'], $targetId, "Tool: $tool → " . ($enabled ? 'on' : 'off'), $ip);
            echo json_encode(['success' => true]);
            break;

        // ─── Admin: Set/Reset Warning Level ─────────────────────
        case 'admin_set_warning':
            $admin = $auth->requireAdmin();
            $targetId = $input['user_id'] ?? '';
            $level = intval($input['level'] ?? 0);
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            PortalDB::resetWarning($targetId, $level);
            PortalDB::logAdmin('warning_changed', $admin['id'], $targetId, "Warning → Level $level", $ip);
            echo json_encode(['success' => true, 'warning' => PortalDB::getWarningInfo($targetId)]);
            break;

        // ─── Backend: Escalate Warning (called by portal_poller) ─
        case 'escalate_warning':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $targetId = $input['user_id'] ?? '';
            $reason = $input['reason'] ?? 'Trolling/Provokation';
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            // Safety: check target is NOT admin
            $target = PortalDB::getUserById($targetId);
            if ($target && $target['role'] === 'admin') {
                echo json_encode(['success' => true, 'level' => 0, 'message' => 'Admins cannot be warned']);
                break;
            }
            $newLevel = PortalDB::escalateWarning($targetId, $reason);
            $info = PortalDB::getWarningInfo($targetId);
            echo json_encode(['success' => true, 'level' => $newLevel, 'warning' => $info]);
            break;

        // ─── Backend: Get Warning Info (called by portal_poller) ─
        case 'get_warning':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $targetId = $input['user_id'] ?? ($_GET['user_id'] ?? '');
            if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
            echo json_encode(['success' => true, 'warning' => PortalDB::getWarningInfo($targetId)]);
            break;

        // ═══════════════════ MODERATION REPORTS ═══════════════════

        // ─── Backend: Report Troll (called by portal_poller) ────
        case 'report_troll':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $userId = $input['user_id'] ?? '';
            $userName = $input['user_name'] ?? '';
            $message = $input['message'] ?? '';
            $trollScore = intval($input['troll_score'] ?? 0);
            $patterns = $input['detected_patterns'] ?? null;
            $convId = $input['conversation_id'] ?? null;
            if (!$userId || !$message) {
                echo json_encode(['error' => 'user_id and message required']);
                break;
            }
            $reportId = PortalDB::createModerationReport($userId, $userName, $message, $trollScore, $patterns, $convId);
            echo json_encode(['success' => true, 'report_id' => $reportId]);
            break;

        // ─── Admin: Get Moderation Reports ──────────────────────
        case 'admin_moderation_reports':
            $auth->requireAdmin();
            $status = $_GET['status'] ?? null;
            $reports = PortalDB::getModerationReports($status);
            $pendingCount = PortalDB::getPendingModerationCount();
            echo json_encode(['success' => true, 'reports' => $reports, 'pending_count' => $pendingCount]);
            break;

        // ─── Admin: Resolve Moderation Report ───────────────────
        case 'admin_resolve_report':
            $admin = $auth->requireAdmin();
            $reportId = $input['report_id'] ?? '';
            $resolution = $input['resolution'] ?? 'dismissed'; // 'reviewed' or 'dismissed'
            $action = $input['action'] ?? null;
            $note = $input['note'] ?? null;
            if (!$reportId) { echo json_encode(['error' => 'report_id required']); break; }
            PortalDB::resolveModerationReport($reportId, $resolution, $action, $note);
            PortalDB::logAdmin('moderation_resolved', $admin['id'], null, "Report $reportId → $resolution" . ($action ? " ($action)" : ''), $ip);
            echo json_encode(['success' => true]);
            break;

        // ─── Admin: Send Warning Message into User's Chat ───────
        case 'admin_send_chat_warning':
            $admin = $auth->requireAdmin();
            $targetUserId = $input['user_id'] ?? '';
            $warningText = $input['message'] ?? '';
            if (!$targetUserId || !$warningText) {
                echo json_encode(['error' => 'user_id and message required']);
                break;
            }
            // Find or create the user's latest conversation
            $convId = PortalDB::getLatestConversationId($targetUserId);
            if (!$convId) {
                // Create a new conversation for the warning
                $convId = PortalDB::uuid();
                PortalDB::get()->prepare(
                    'INSERT INTO portal_conversations (id, user_id, title, created_at) VALUES (?, ?, ?, NOW())'
                )->execute([$convId, $targetUserId, '⚠️ Admin-Nachricht']);
            }
            // Insert the warning as an assistant message (from Ailey/Admin)
            $fullMsg = "⚠️ **Nachricht vom Admin:**\n\n" . $warningText;
            PortalDB::addMessage($convId, 'assistant', $fullMsg, 'serious');
            PortalDB::updateConversation($convId);
            PortalDB::logAdmin('chat_warning_sent', $admin['id'], $targetUserId, mb_substr($warningText, 0, 200), $ip);
            echo json_encode(['success' => true, 'conversation_id' => $convId]);
            break;

        // ─── Admin: Get Pending Moderation Count (for badge) ────
        case 'admin_moderation_count':
            $auth->requireAdmin();
            echo json_encode(['success' => true, 'count' => PortalDB::getPendingModerationCount()]);
            break;

        // ─── User: Get own tool access (which tools are enabled) ─
        case 'my_tools':
            $user = $auth->requireAuth();
            $tools = PortalDB::getToolAccess($user['id']);
            $imgQuota = PortalDB::getImageQuota($user['id']);
            $songQuota = PortalDB::getSongQuota($user['id']);
            $vInfo = PortalDB::getVdollarsInfo($user['id']);
            echo json_encode([
                'success' => true,
                'tools' => $tools,
                'image_quota' => $imgQuota,
                'song_quota' => $songQuota,
                'vdollars' => $vInfo,
            ]);
            break;

        // ─── User Generations: Store image/song record ──────────
        case 'store_user_generation':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $targetId = $input['user_id'] ?? '';
            $type = $input['type'] ?? '';
            if (!$targetId || !in_array($type, ['image', 'song'], true)) {
                echo json_encode(['error' => 'user_id and type required']);
                break;
            }
            $genId = PortalDB::addUserGeneration($targetId, $type, $input);
            echo json_encode(['success' => true, 'id' => $genId]);
            break;

        // ─── User Generations: List own generations ─────────────
        case 'my_generations':
            $user = $auth->requireAuth();
            $type = $_GET['type'] ?? null;
            if ($type && !in_array($type, ['image', 'song'], true)) $type = null;
            $gens = PortalDB::getUserGenerations($user['id'], $type);
            echo json_encode(['success' => true, 'generations' => $gens]);
            break;

        // ─── User Generations: Delete own generation ────────────
        case 'delete_generation':
            $user = $auth->requireAuth();
            $genId = $input['id'] ?? '';
            if (!$genId) { echo json_encode(['error' => 'id required']); break; }
            $deleted = PortalDB::deleteUserGeneration($genId, $user['id']);
            echo json_encode(['success' => $deleted]);
            break;

        // ─── Available LoRAs (portal excludes NSFW) ────────────
        case 'available_loras':
            $auth->requireAuth();
            // Hardcoded list matching image_generator.py — portal excludes nsfw
            $loras = [
                'realism' => ['description' => 'Fotorealismus — scharfe Details, natürliche Haut', 'trigger' => 'photo realistic'],
                'anime'   => ['description' => 'Anime/Manga-Stil — lebendige Farben, große Augen', 'trigger' => 'anime style'],
            ];
            echo json_encode(['success' => true, 'loras' => $loras]);
            break;

        // ─── Generate Image (direct tool, not chat-based) ──────
        // User submits from the Image-Gen tab → queued for Ailey Core
        case 'generate_image':
            $user = $auth->requireAuth();
            if (PortalDB::getUserTier($user['id']) === 'public') {
                echo json_encode(['error' => 'tier_restricted', 'message' => 'Bildgenerierung ist nur für eingeladene Nutzer verfügbar.']);
                break;
            }
            $tools = PortalDB::getToolAccess($user['id']);
            if (!$tools['image_gen']) {
                echo json_encode(['error' => 'tool_not_enabled', 'message' => 'Bildgenerierung ist für dich nicht freigeschaltet.']);
                break;
            }
            // V$ cost for image generation (15 V$)
            if (!PortalDB::spendVdollars($user['id'], 15, 'image_generation')) {
                $vInfo = PortalDB::getVdollarsInfo($user['id']);
                echo json_encode([
                    'error' => 'insufficient_vdollars',
                    'message' => 'Nicht genug V$! Du hast ' . $vInfo['balance'] . ' V$, brauchst aber 15 V$.',
                    'balance' => $vInfo['balance'],
                ]);
                break;
            }
            $prompt = trim($input['prompt'] ?? '');
            if (!$prompt) { echo json_encode(['error' => 'prompt required']); break; }
            $ar = $input['aspect_ratio'] ?? '1:1';
            if (!in_array($ar, ['1:1', '16:9', '9:16', '4:3', '3:4'], true)) $ar = '1:1';
            $steps = max(1, min(12, intval($input['steps'] ?? 9)));
            $selfie = (bool)($input['ailey_selfie'] ?? false);
            // Sanitise LoRA IDs (only non-empty strings, no NSFW via portal)
            $lora_ids = [];
            if (!empty($input['lora_ids']) && is_array($input['lora_ids'])) {
                $allowed = ['realism', 'anime']; // no NSFW via portal
                $lora_ids = array_values(array_intersect(array_filter($input['lora_ids'], 'is_string'), $allowed));
                $lora_ids = array_slice($lora_ids, 0, 2);
            }
            // Queue as a generation job via portal_offline_queue
            $queueId = PortalDB::uuid();
            $context = json_encode([
                'type' => 'image_gen_tool',
                'prompt' => $prompt,
                'aspect_ratio' => $ar,
                'steps' => $steps,
                'ailey_selfie' => $selfie,
                'lora_ids' => $lora_ids,
                'user_name' => $user['display_name'],
                'user_id' => $user['id'],
                'language' => $user['language'] ?? 'de',
            ]);
            $stmt = PortalDB::get()->prepare(
                'INSERT INTO portal_offline_queue (id, user_id, conversation_id, message, context, status) VALUES (?, ?, ?, ?, ?, ?)'
            );
            $stmt->execute([$queueId, $user['id'], '', "__tool:image_gen:$prompt", $context, 'pending']);
            echo json_encode(['success' => true, 'queue_id' => $queueId]);
            break;

        // ─── Generate Song (direct tool, not chat-based) ───────
        case 'generate_song':
            $user = $auth->requireAuth();
            if (PortalDB::getUserTier($user['id']) === 'public') {
                echo json_encode(['error' => 'tier_restricted', 'message' => 'Songgenerierung ist nur für eingeladene Nutzer verfügbar.']);
                break;
            }
            $tools = PortalDB::getToolAccess($user['id']);
            if (!$tools['song_gen']) {
                echo json_encode(['error' => 'tool_not_enabled', 'message' => 'Songgenerierung ist für dich nicht freigeschaltet.']);
                break;
            }
            // V$ cost for song generation (30 V$)
            if (!PortalDB::spendVdollars($user['id'], 30, 'song_generation')) {
                $vInfo = PortalDB::getVdollarsInfo($user['id']);
                echo json_encode([
                    'error' => 'insufficient_vdollars',
                    'message' => 'Nicht genug V$! Du hast ' . $vInfo['balance'] . ' V$, brauchst aber 30 V$.',
                    'balance' => $vInfo['balance'],
                ]);
                break;
            }
            $lyrics = trim($input['lyrics'] ?? '');
            $tags = trim($input['tags'] ?? '');
            $title = trim($input['title'] ?? '');
            if (!$lyrics) { echo json_encode(['error' => 'lyrics required']); break; }
            $duration = max(30, min(480, intval($input['duration'] ?? 180)));
            $steps = max(4, min(30, intval($input['steps'] ?? 20)));
            // Queue as a generation job
            $queueId = PortalDB::uuid();
            $context = json_encode([
                'type' => 'song_gen_tool',
                'title' => $title,
                'lyrics' => $lyrics,
                'tags' => $tags,
                'duration' => $duration,
                'steps' => $steps,
                'user_name' => $user['display_name'],
                'user_id' => $user['id'],
                'language' => $user['language'] ?? 'de',
            ]);
            $stmt = PortalDB::get()->prepare(
                'INSERT INTO portal_offline_queue (id, user_id, conversation_id, message, context, status) VALUES (?, ?, ?, ?, ?, ?)'
            );
            $stmt->execute([$queueId, $user['id'], '', "__tool:song_gen:" . mb_substr($lyrics, 0, 100), $context, 'pending']);
            echo json_encode(['success' => true, 'queue_id' => $queueId]);
            break;

        // ─── Check generation job status (image or song) ───────
        case 'generation_status':
            $user = $auth->requireAuth();
            $queueId = $_GET['queue_id'] ?? ($input['queue_id'] ?? '');
            if (!$queueId) { echo json_encode(['error' => 'queue_id required']); break; }
            $stmt = PortalDB::get()->prepare(
                'SELECT id, status, reply, image_url, mood, processed_at FROM portal_offline_queue WHERE id = ? AND user_id = ? LIMIT 1'
            );
            $stmt->execute([$queueId, $user['id']]);
            $job = $stmt->fetch(\PDO::FETCH_ASSOC);
            if (!$job) { echo json_encode(['error' => 'not_found']); break; }
            echo json_encode(['success' => true, 'job' => $job]);
            break;

        // ─── Upload user-generated file (called by portal_poller) ──
        case 'upload_user_gen_file':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            if (empty($_FILES['file'])) {
                echo json_encode(['error' => 'No file uploaded']);
                break;
            }
            $userId = $_POST['user_id'] ?? '';
            $type   = $_POST['type'] ?? 'image';  // 'image' or 'song'
            if (!$userId) { echo json_encode(['error' => 'user_id required']); break; }
            // Sanitize
            $userId = preg_replace('/[^a-zA-Z0-9_-]/', '', $userId);
            $type   = preg_replace('/[^a-z]/', '', $type);
            // Build target directory: uploads/user_gen/{user_id}/{type}/
            $baseDir = __DIR__ . '/uploads/user_gen/' . $userId . '/' . $type;
            if (!is_dir($baseDir)) {
                mkdir($baseDir, 0755, true);
            }
            // Safe filename
            $origName = basename($_FILES['file']['name']);
            $ext = strtolower(pathinfo($origName, PATHINFO_EXTENSION));
            $allowed = ['png', 'jpg', 'jpeg', 'webp', 'mp3', 'wav', 'ogg', 'mp4'];
            if (!in_array($ext, $allowed)) { $ext = 'bin'; }
            $safeName = preg_replace('/[^a-zA-Z0-9_.-]/', '_', pathinfo($origName, PATHINFO_FILENAME));
            $finalName = $safeName . '.' . $ext;
            $destPath = $baseDir . '/' . $finalName;
            // Avoid overwrite
            if (file_exists($destPath)) {
                $finalName = $safeName . '_' . time() . '.' . $ext;
                $destPath = $baseDir . '/' . $finalName;
            }
            if (move_uploaded_file($_FILES['file']['tmp_name'], $destPath)) {
                // Build public URL
                $proto = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
                $host = $_SERVER['HTTP_HOST'] ?? 'hey-ailey.com';
                $relPath = 'uploads/user_gen/' . $userId . '/' . $type . '/' . $finalName;
                $url = $proto . '://' . $host . '/' . $relPath;
                echo json_encode(['success' => true, 'url' => $url, 'filename' => $finalName]);
            } else {
                echo json_encode(['error' => 'Failed to move uploaded file']);
            }
            break;

        // ═══════════════════ ARTIFACTS (Code + SVGs) ═════════════
        case 'artifacts':
            $user = $auth->requireAuth();
            $type = $_GET['type'] ?? ($input['type'] ?? null);
            if ($type && !in_array($type, ['code', 'svg', 'song', 'image'])) $type = null;
            $limit = intval($_GET['limit'] ?? ($input['limit'] ?? 100));
            $counts = PortalDB::getArtifactCountsByType($user['id']);
            $artifacts = ($limit > 0) ? PortalDB::listArtifacts($user['id'], $type, $limit) : [];
            echo json_encode(['success' => true, 'artifacts' => $artifacts, 'counts' => $counts]);
            break;
        case 'artifact':
            $user = $auth->requireAuth();
            $id = $_GET['id'] ?? '';
            if (!$id) { echo json_encode(['error' => 'id required']); break; }
            $artifact = PortalDB::getArtifact($id, $user['id']);
            if (!$artifact) { echo json_encode(['error' => 'not_found']); break; }
            echo json_encode(['success' => true, 'artifact' => $artifact]);
            break;
        case 'artifact_download':
            $user = $auth->requireAuth();
            $id = $_GET['id'] ?? '';
            if (!$id) { http_response_code(400); echo 'id required'; break; }
            $artifact = PortalDB::getArtifact($id, $user['id']);
            if (!$artifact) { http_response_code(404); echo 'not found'; break; }
            // For images: content is a URL — redirect to it
            if ($artifact['type'] === 'image') {
                header('Location: ' . $artifact['content']);
                http_response_code(302);
                exit;
            }
            $ext = $artifact['type'] === 'svg' ? 'svg' : ($artifact['language'] ?: 'txt');
            $ext = preg_replace('/[^a-z0-9]/', '', strtolower($ext));
            $fname = preg_replace('/[^a-zA-Z0-9_.-]/', '_', $artifact['title'] ?: 'artifact') . '.' . $ext;
            $mime = $artifact['type'] === 'svg' ? 'image/svg+xml' : 'text/plain';
            header('Content-Type: ' . $mime);
            header('Content-Disposition: attachment; filename="' . $fname . '"');
            echo $artifact['content'];
            exit;

        // ═══════════════════ USER GALLERY SUBMISSIONS ════════════
        case 'submit_to_gallery':
            $user = $auth->requireAuth();
            $artifactId = $input['artifact_id'] ?? '';
            if (!$artifactId) {
                echo json_encode(['error' => 'artifact_id required']);
                break;
            }
            $artifact = PortalDB::getArtifact($artifactId, $user['id']);
            if (!$artifact) {
                echo json_encode(['error' => 'artifact_not_found']);
                break;
            }
            $galleryType = $artifact['type']; // code, svg, song, image
            $result = PortalDB::submitArtifactToGallery(
                $user['id'], $artifactId, $galleryType,
                $artifact['title'] ?: 'Untitled',
                $artifact['content'],
                $artifact['language']
            );
            if ($result === -1) {
                echo json_encode(['error' => 'already_submitted']);
            } elseif ($result > 0) {
                echo json_encode(['success' => true, 'gallery_id' => $result]);
            } else {
                echo json_encode(['error' => 'submission_failed']);
            }
            break;

        case 'delete_gallery_item':
            $user = $auth->requireAuth();
            $itemId = (int)($input['gallery_item_id'] ?? 0);
            if (!$itemId) {
                echo json_encode(['error' => 'gallery_item_id required']);
                break;
            }
            $isAdmin = ($user['role'] === 'admin');
            $result = PortalDB::deleteGalleryItem($itemId, $user['id'], $isAdmin);
            echo json_encode(['success' => $result]);
            break;

        // ═══════════════════ PUBLIC ART SITE ════════════════════

        // ─── push_blog_post: Ailey Core pushes a new blog post ──
        case 'push_blog_post':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $title = trim($input['title'] ?? '');
            $contentMd = trim($input['content_md'] ?? '');
            $topic = $input['topic'] ?? null;
            $mood = $input['mood'] ?? null;
            $lang = $input['language'] ?? 'de';
            $imageUrl = $input['image_url'] ?? null;
            if (!$title || !$contentMd) {
                echo json_encode(['error' => 'title and content_md required']);
                break;
            }
            // Generate slug from title
            $slug = preg_replace('/[^a-z0-9]+/', '-', strtolower(
                iconv('UTF-8', 'ASCII//TRANSLIT//IGNORE', $title)
            ));
            $slug = trim($slug, '-');
            $slug .= '-' . date('Ymd');
            $id = PortalDB::addBlogPost($slug, $title, $contentMd, $topic, $mood, $lang, $imageUrl);
            echo json_encode(['success' => true, 'id' => $id, 'slug' => $slug]);
            break;

        // ─── unpublish_blog_post: Hide a blog post by ID (Portal-Key) ──
        case 'unpublish_blog_post':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $postId = (int)($input['id'] ?? $_GET['id'] ?? 0);
            if (!$postId) { echo json_encode(['error' => 'id required']); break; }
            $stmt = PortalDB::get()->prepare('UPDATE ailey_blog_posts SET published = 0, updated_at = NOW() WHERE id = ?');
            $stmt->execute([$postId]);
            echo json_encode(['success' => true, 'id' => $postId, 'action' => 'unpublished']);
            break;

        // ─── update_blog_post: Update existing blog post by ID ──
        case 'update_blog_post':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $postId = (int)($input['id'] ?? 0);
            $contentMd = trim($input['content_md'] ?? '');
            $title = trim($input['title'] ?? '');
            if (!$postId || !$contentMd) {
                echo json_encode(['error' => 'id and content_md required']);
                break;
            }
            $ok = PortalDB::updateBlogPost($postId, $title ?: null, $contentMd);
            echo json_encode(['success' => $ok]);
            break;

        // ─── set_blog_image: Set or clear the image_url for a blog post ──
        case 'set_blog_image':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $postId = (int)($input['id'] ?? 0);
            if (!$postId) {
                echo json_encode(['error' => 'id required']);
                break;
            }
            $imageUrl = $input['image_url'] ?? null; // null = clear
            $stmt = PortalDB::get()->prepare('UPDATE ailey_blog_posts SET image_url = ?, updated_at = NOW() WHERE id = ?');
            $stmt->execute([$imageUrl, $postId]);
            echo json_encode(['success' => true, 'id' => $postId, 'image_url' => $imageUrl]);
            break;

        // ─── blog_posts_without_image: Get blog posts that have no image ──
        case 'blog_posts_without_image':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $stmt = PortalDB::get()->prepare(
                'SELECT id, slug, title, topic, mood, LEFT(content_md, 500) as excerpt '
                . 'FROM ailey_blog_posts WHERE published = 1 AND (image_url IS NULL OR image_url = \'\') '
                . 'ORDER BY published_at DESC'
            );
            $stmt->execute();
            $posts = $stmt->fetchAll(\PDO::FETCH_ASSOC);
            echo json_encode(['success' => true, 'posts' => $posts]);
            break;

        // ─── unpublish_gallery_item: Ailey Core removes a gallery item (Portal-Key) ──
        case 'unpublish_gallery_item':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $itemId = (int)($input['id'] ?? 0);
            $permanent = (bool)($input['permanent'] ?? false);
            if (!$itemId) {
                echo json_encode(['error' => 'id required']);
                break;
            }
            if ($permanent) {
                PortalDB::adminUnpublishGalleryItem($itemId, true);
                PortalDB::adminDeleteGalleryItem($itemId);
                echo json_encode(['success' => true, 'action' => 'deleted_and_blocked']);
            } else {
                PortalDB::adminUnpublishGalleryItem($itemId, true);
                echo json_encode(['success' => true, 'action' => 'unpublished_and_blocked']);
            }
            break;

        // ─── push_gallery_item: Ailey Core pushes song/image/book ──
        case 'push_gallery_item':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $type = $input['type'] ?? '';
            $title = trim($input['title'] ?? '');
            if (!$type || !$title || !in_array($type, ['song', 'image', 'svg', 'book', 'code'])) {
                echo json_encode(['error' => 'valid type (song|image|svg|book|code) and title required']);
                break;
            }
            // Auto-tag NSFW songs on upload
            $meta = $input['metadata'] ?? null;
            $blockPublish = false;
            if ($type === 'song' && !empty($input['content_text'])) {
                $fullText = $title . "\n" . $input['content_text'];
                // Simon + NSFW → never publish (not even censored)
                if (NsfwFilter::containsSimonNsfw($fullText)) {
                    $blockPublish = true;
                    if (!is_array($meta)) $meta = [];
                    $meta['is_nsfw'] = true;
                    $meta['blocked_reason'] = 'simon_nsfw';
                } elseif (NsfwFilter::isSongNsfw($input['content_text'])) {
                    if (!is_array($meta)) $meta = [];
                    $meta['is_nsfw'] = true;
                }
            }
            $id = PortalDB::addGalleryItem(
                $type, $title,
                $input['description'] ?? null,
                $input['content_text'] ?? null,
                $input['file_url'] ?? null,
                $meta,
                $input['source_id'] ?? null,
                $input['language'] ?? 'de'
            );
            // If Simon+NSFW, immediately unpublish (but keep in DB for admin review)
            if ($blockPublish && $id > 0) {
                $stmt = PortalDB::get()->prepare('UPDATE ailey_gallery_items SET published = 0 WHERE id = ?');
                $stmt->execute([$id]);
            }
            echo json_encode(['success' => true, 'id' => $id, 'blocked' => $blockPublish]);
            break;

        // ─── deduplicate_gallery: Remove duplicate songs, keep best ──
        case 'deduplicate_gallery':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $deleted = PortalDB::deduplicateGallerySongs();
            echo json_encode(['success' => true, 'deleted' => $deleted]);
            break;

        // ─── core_delete_gallery_item: Portal-key-based delete for cleanup ──
        case 'core_delete_gallery_item':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $itemId = (int)($input['id'] ?? 0);
            if (!$itemId) {
                echo json_encode(['error' => 'id required']);
                break;
            }
            $stmt = PortalDB::get()->prepare('DELETE FROM ailey_gallery_items WHERE id = ?');
            $stmt->execute([$itemId]);
            $affected = $stmt->rowCount();
            echo json_encode(['success' => $affected > 0, 'id' => $itemId, 'deleted' => $affected]);
            break;

        // ─── core_nuke_all_songs: Portal-key-based wipe ALL songs for full resync ──
        case 'core_nuke_all_songs':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $confirm = $input['confirm'] ?? '';
            if ($confirm !== 'YES_NUKE_ALL_SONGS') {
                echo json_encode(['error' => 'must pass confirm=YES_NUKE_ALL_SONGS']);
                break;
            }
            $stmt = PortalDB::get()->prepare("DELETE FROM ailey_gallery_items WHERE item_type = 'song'");
            $stmt->execute();
            $affected = $stmt->rowCount();
            // Also clear blocked source_ids for songs so resync works (table may not exist)
            try {
                $stmt2 = PortalDB::get()->prepare("DELETE FROM ailey_gallery_blocked WHERE source_id LIKE 'song_%'");
                $stmt2->execute();
            } catch (\Exception $e) { /* table may not exist, ignore */ }
            echo json_encode(['success' => true, 'deleted_songs' => $affected]);
            break;

        // ─── update_gallery_type: Fix item_type for a gallery item ──
        case 'update_gallery_type':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $gId = (int)($input['id'] ?? 0);
            $gType = trim($input['type'] ?? '');
            if (!$gId || !$gType || !in_array($gType, ['song', 'image', 'svg', 'book', 'code'])) {
                echo json_encode(['error' => 'valid id and type required']);
                break;
            }
            $stmt = PortalDB::get()->prepare('UPDATE ailey_gallery_items SET item_type = ? WHERE id = ?');
            $stmt->execute([$gType, $gId]);
            echo json_encode(['success' => true, 'id' => $gId, 'type' => $gType]);
            break;

        // ─── update_gallery_title: Fix title for a gallery item ──
        case 'update_gallery_title':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $gId = (int)($input['id'] ?? 0);
            $gTitle = trim($input['title'] ?? '');
            if (!$gId || !$gTitle) {
                echo json_encode(['error' => 'valid id and title required']);
                break;
            }
            $stmt = PortalDB::get()->prepare('UPDATE ailey_gallery_items SET title = ? WHERE id = ?');
            $stmt->execute([$gTitle, $gId]);
            echo json_encode(['success' => true, 'id' => $gId, 'title' => $gTitle]);
            break;

        // ─── run_migration: One-shot schema migrations ──
        case 'run_migration':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $results = [];
            try {
                // Add 'code' to item_type ENUM if missing
                PortalDB::get()->exec(
                    "ALTER TABLE ailey_gallery_items MODIFY COLUMN item_type ENUM('song','image','svg','book','code') NOT NULL"
                );
                $results[] = 'item_type ENUM updated to include code';
            } catch (Exception $e) {
                $results[] = 'item_type ENUM: ' . $e->getMessage();
            }
            // 004: User Memories table for cross-session knowledge
            try {
                PortalDB::get()->exec("
                    CREATE TABLE IF NOT EXISTS `portal_user_memories` (
                        `id`                      CHAR(36)     NOT NULL PRIMARY KEY,
                        `user_id`                 CHAR(36)     NOT NULL,
                        `memory_text`             VARCHAR(500) NOT NULL,
                        `category`                ENUM('preference','fact','topic','relationship','goal','style') NOT NULL DEFAULT 'fact',
                        `source_conversation_id`  CHAR(36)     DEFAULT NULL,
                        `confidence`              FLOAT        NOT NULL DEFAULT 1.0,
                        `created_at`              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        `last_referenced`         DATETIME     DEFAULT NULL,
                        `superseded_by`           CHAR(36)     DEFAULT NULL,
                        INDEX `idx_user`          (`user_id`),
                        INDEX `idx_user_active`   (`user_id`, `confidence`),
                        INDEX `idx_user_cat`      (`user_id`, `category`),
                        INDEX `idx_superseded`    (`superseded_by`),
                        FOREIGN KEY (`user_id`) REFERENCES `portal_users`(`id`) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                ");
                $results[] = 'portal_user_memories table created (or already exists)';
            } catch (Exception $e) {
                $results[] = 'portal_user_memories: ' . $e->getMessage();
            }
            echo json_encode(['success' => true, 'migrations' => $results]);
            break;

        // ─── upload_gallery_file: Ailey Core uploads image/file for gallery item ──
        case 'upload_gallery_file':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $fileData = $input['file_data'] ?? '';  // base64-encoded
            $filename = trim($input['filename'] ?? '');
            $mimeType = $input['mime_type'] ?? 'image/png';
            if (!$fileData || !$filename) {
                echo json_encode(['error' => 'file_data and filename required']);
                break;
            }
            // Sanitize filename
            $filename = preg_replace('/[^a-zA-Z0-9._-]/', '_', $filename);
            $uploadDir = __DIR__ . '/uploads/gallery';
            if (!is_dir($uploadDir)) {
                mkdir($uploadDir, 0755, true);
            }
            $filePath = $uploadDir . '/' . $filename;
            $decoded = base64_decode($fileData, true);
            if ($decoded === false || strlen($decoded) < 100) {
                echo json_encode(['error' => 'invalid base64 data']);
                break;
            }
            // Max 15MB (increased for MP3 audio files)
            if (strlen($decoded) > 15 * 1024 * 1024) {
                echo json_encode(['error' => 'file too large (max 15MB)']);
                break;
            }
            file_put_contents($filePath, $decoded);
            $publicUrl = '/uploads/gallery/' . $filename;
            echo json_encode(['success' => true, 'url' => $publicUrl, 'size' => strlen($decoded)]);
            break;

        // ─── push_book_chapter: Ailey Core pushes a chapter ────
        case 'push_book_chapter':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $bookSourceId = trim($input['book_source_id'] ?? '');
            $chapterNum = (int)($input['chapter_num'] ?? 0);
            $chapterTitle = $input['chapter_title'] ?? null;
            $contentMd = $input['content_md'] ?? '';
            $contentHash = $input['content_hash'] ?? '';
            $wordCount = (int)($input['word_count'] ?? 0);
            $isRevised = (bool)($input['is_revised'] ?? false);
            if (!$bookSourceId || !$chapterNum || !$contentMd) {
                echo json_encode(['error' => 'book_source_id, chapter_num, content_md required']);
                break;
            }
            $result = PortalDB::upsertBookChapter(
                $bookSourceId, $chapterNum, $chapterTitle,
                $contentMd, $contentHash, $wordCount, $isRevised
            );
            echo json_encode(['success' => true, 'result' => $result]);
            break;

        // ─── get_book_chapters: Public — list chapters for a book ──
        case 'get_book_chapters':
            $bookSourceId = trim($_GET['book_source_id'] ?? '');
            if (!$bookSourceId) {
                echo json_encode(['error' => 'book_source_id required']);
                break;
            }
            $chapters = PortalDB::getBookChapters($bookSourceId);
            echo json_encode(['success' => true, 'chapters' => $chapters]);
            break;

        // ─── get_book_chapter: Public — single chapter content ──
        case 'get_book_chapter':
            $bookSourceId = trim($_GET['book_source_id'] ?? '');
            $chapterNum = (int)($_GET['chapter_num'] ?? 0);
            if (!$bookSourceId || !$chapterNum) {
                echo json_encode(['error' => 'book_source_id and chapter_num required']);
                break;
            }
            $chapter = PortalDB::getBookChapter($bookSourceId, $chapterNum);
            if (!$chapter) {
                http_response_code(404);
                echo json_encode(['error' => 'chapter not found']);
                break;
            }
            echo json_encode(['success' => true, 'chapter' => $chapter]);
            break;

        // ─── push_activity: Ailey Core pushes a feed event ──────
        case 'push_activity':
            if (!verifyPortalKey($config)) {
                http_response_code(401);
                echo json_encode(['error' => 'unauthorized']);
                break;
            }
            $eventType = trim($input['event_type'] ?? '');
            $title = trim($input['title'] ?? '');
            if (!$eventType || !$title) {
                echo json_encode(['error' => 'event_type and title required']);
                break;
            }
            $id = PortalDB::addActivity(
                $eventType, $title,
                $input['url'] ?? null,
                $input['preview'] ?? null,
                $input['emoji'] ?? null
            );
            echo json_encode(['success' => true, 'id' => $id]);
            break;

        // ─── get_blog_posts: Public — paginated blog listing ────
        case 'get_blog_posts':
            $limit = min(max((int)($_GET['limit'] ?? 10), 1), 50);
            $offset = max((int)($_GET['offset'] ?? 0), 0);
            $posts = PortalDB::getBlogPosts($limit, $offset);
            $total = PortalDB::countBlogPosts();
            echo json_encode(['success' => true, 'posts' => $posts, 'total' => $total]);
            break;

        // ─── get_blog_post: Public — single post by slug ────────
        case 'get_blog_post':
            $slug = $_GET['slug'] ?? '';
            if (!$slug) { echo json_encode(['error' => 'slug required']); break; }
            $post = PortalDB::getBlogPostBySlug($slug);
            if (!$post) {
                http_response_code(404);
                echo json_encode(['error' => 'not_found']);
                break;
            }
            echo json_encode(['success' => true, 'post' => $post]);
            break;

        // ─── get_intro_data: Public — dynamic data for cinematic intro ──
        // Server-side JSON cache: refresh every 10 min, so intro works even if DB hiccups
        case 'get_intro_data':
            $cacheFile = __DIR__ . '/cache_intro_data.json';
            $cacheTTL  = 600; // 10 minutes
            if (file_exists($cacheFile) && (time() - filemtime($cacheFile)) < $cacheTTL) {
                header('X-Intro-Cache: HIT');
                echo file_get_contents($cacheFile);
                break;
            }
            header('X-Intro-Cache: MISS');

            // 5 latest images (selfies preferred, fallback to any image)
            $selfies = PortalDB::get()->query(
                "SELECT id, title, file_url, metadata_json, created_at FROM ailey_gallery_items
                 WHERE item_type = 'image' AND published = 1 AND file_url IS NOT NULL
                   AND (source_id LIKE '%SELFIE%' AND source_id NOT LIKE '%BLOG%')
                 ORDER BY created_at DESC LIMIT 5"
            )->fetchAll(PDO::FETCH_ASSOC);
            if (count($selfies) < 5) {
                $have = array_column($selfies, 'id');
                $exclude = $have ? 'AND id NOT IN ('.implode(',', $have).')' : '';
                $fill = PortalDB::get()->query(
                    "SELECT id, title, file_url, metadata_json, created_at FROM ailey_gallery_items
                     WHERE item_type = 'image' AND published = 1 AND file_url IS NOT NULL
                       $exclude
                     ORDER BY created_at DESC LIMIT ".(5 - count($selfies))
                )->fetchAll(PDO::FETCH_ASSOC);
                $selfies = array_merge($selfies, $fill);
            }
            $introImages = [];
            foreach ($selfies as $img) {
                $introImages[] = [
                    'url'   => $img['file_url'],
                    'title' => $img['title'],
                    'date'  => $img['created_at'],
                ];
            }

            // Latest outputs for keyword ticker — smart per-type filtering
            // Songs: full title (no "Song" in name), Images: NEVER, Books: single noun, SVG/Code: full
            $latest = PortalDB::get()->query(
                "SELECT title, item_type, content_text, created_at FROM ailey_gallery_items
                 WHERE published = 1 AND title != '' AND title != 'Unbenannt' AND title != 'Untitled'
                   AND item_type != 'image'
                   AND NOT (item_type = 'song' AND title LIKE '%Song%')
                 ORDER BY created_at DESC LIMIT 40"
            )->fetchAll(PDO::FETCH_ASSOC);

            // German/English stop words to skip when extracting a noun from book titles
            $stopWords = array_flip(['der','die','das','ein','eine','und','oder','aber','ist','sind',
                'war','von','zu','für','mit','in','im','am','an','auf','aus','bei','nach','über',
                'the','a','an','and','or','but','is','are','was','of','to','for','with','in','on',
                'at','by','from','my','your','his','her','its','our','their','this','that',
                'mein','dein','sein','ihr','ich','du','er','sie','es','wir','nicht','kein','keine',
                'wie','so','wenn','als','noch','nur','auch','schon','was','wer','wo','how','what',
                'i','me','you','he','she','we','they','it','been','be','have','had','has','no','not']);

            $keywords = [];
            $seen = []; // deduplicate
            foreach ($latest as $item) {
                $title = trim($item['title']);
                // NSFW title check — skip entirely
                if (NsfwFilter::isLineNsfw($title)) continue;

                // Strip markdown artefacts: **, *, ", leading/trailing quotes
                $title = preg_replace('/^\*{1,2}\s*|\s*\*{1,2}$/', '', $title);
                $title = trim($title, ' "\'*');
                if ($title === '') continue;

                // Skip registry IDs / hashes / numeric-only titles
                if (preg_match('/^(registry_|[0-9a-f]{16,}$|[0-9]+$)/i', $title)) continue;

                $type = $item['item_type'];
                $text = $title;

                if ($type === 'book') {
                    // Extract the most representative single word (longest non-stop-word ≥ 4 chars)
                    $words = preg_split('/[\s\-–—:,;.!?()]+/', $title, -1, PREG_SPLIT_NO_EMPTY);
                    $best = null;
                    $bestLen = 0;
                    foreach ($words as $w) {
                        $wLower = mb_strtolower($w);
                        if (isset($stopWords[$wLower])) continue;
                        if (mb_strlen($w) < 4) continue;
                        // Prefer longer words (likely nouns)
                        if (mb_strlen($w) > $bestLen) {
                            $best = $w;
                            $bestLen = mb_strlen($w);
                        }
                    }
                    if (!$best) continue; // no usable word found → skip
                    $text = ucfirst($best);
                }

                $key = mb_strtolower($text);
                if (isset($seen[$key])) continue;
                $seen[$key] = true;

                $keywords[] = [
                    'text' => $text,
                    'type' => $type,
                ];
                if (count($keywords) >= 20) break;
            }

            // Gallery stats for endframe
            $stats = PortalDB::getGalleryStats();

            $introPayload = json_encode([
                'success'  => true,
                'images'   => $introImages,
                'keywords' => $keywords,
                'stats'    => $stats,
            ]);
            // Write cache file (atomic via tmp + rename)
            $tmpFile = $cacheFile . '.tmp';
            file_put_contents($tmpFile, $introPayload);
            rename($tmpFile, $cacheFile);
            echo $introPayload;
            break;

        // ─── get_gallery: Public — paginated gallery ────────────
        case 'get_gallery':
            $type = $_GET['type'] ?? null;
            if ($type && !in_array($type, ['song', 'image', 'svg', 'book'])) $type = null;
            $limit = min(max((int)($_GET['limit'] ?? 20), 1), 100);
            $offset = max((int)($_GET['offset'] ?? 0), 0);
            $items = PortalDB::getGalleryItems($type, $limit, $offset);
            $stats = PortalDB::getGalleryStats();
            // NSFW: censor song lyrics for non-logged-in API requests
            $apiUser = $auth->getCurrentUser();
            foreach ($items as &$gi) {
                if ($gi['item_type'] === 'song' && !empty($gi['content_text'])) {
                    $nsfwRes = NsfwFilter::censorSongContent($gi['content_text']);
                    $gi['is_nsfw'] = $nsfwRes['is_nsfw'];
                    if (!$apiUser && $nsfwRes['is_nsfw']) {
                        $gi['content_text'] = $nsfwRes['content'];
                        $gi['censored_lines'] = $nsfwRes['censored_lines'];
                    }
                }
            }
            unset($gi);
            echo json_encode(['success' => true, 'items' => $items, 'stats' => $stats]);
            break;

        // ─── get_gallery_item: Public — single item detail ──────
        case 'get_gallery_item':
            $id = (int)($_GET['id'] ?? 0);
            if (!$id) { echo json_encode(['error' => 'id required']); break; }
            $item = PortalDB::getGalleryItem($id);
            if (!$item) {
                http_response_code(404);
                echo json_encode(['error' => 'not_found']);
                break;
            }
            // NSFW: censor for non-logged-in requests
            if ($item['item_type'] === 'song' && !empty($item['content_text'])) {
                $nsfwRes = NsfwFilter::censorSongContent($item['content_text']);
                $item['is_nsfw'] = $nsfwRes['is_nsfw'];
                $apiUser = $auth->getCurrentUser();
                if (!$apiUser && $nsfwRes['is_nsfw']) {
                    $item['content_text'] = $nsfwRes['content'];
                    $item['censored_lines'] = $nsfwRes['censored_lines'];
                }
            }
            echo json_encode(['success' => true, 'item' => $item]);
            break;

        // ─── get_activity_feed: Public — paginated timeline ─────
        case 'get_activity_feed':
            $limit = min(max((int)($_GET['limit'] ?? 30), 1), 100);
            $offset = max((int)($_GET['offset'] ?? 0), 0);
            $feed = PortalDB::getActivityFeed($limit, $offset);
            $total = PortalDB::countActivities();
            echo json_encode(['success' => true, 'feed' => $feed, 'total' => $total]);
            break;

        // ─── admin_gallery: list all gallery items for admin ─────
        case 'admin_gallery':
            $auth->requireAuth();
            $me = $auth->getCurrentUser();
            if (!$me || $me['role'] !== 'admin') {
                http_response_code(403);
                echo json_encode(['error' => 'admin_only']);
                break;
            }
            $items = PortalDB::adminGetAllGalleryItems(200, 0);
            echo json_encode(['success' => true, 'items' => $items]);
            break;

        // ─── admin_pending_submissions: list pending user submissions ──
        case 'admin_pending_submissions':
            $auth->requireAuth();
            $me = $auth->getCurrentUser();
            if (!$me || $me['role'] !== 'admin') {
                http_response_code(403);
                echo json_encode(['error' => 'admin_only']);
                break;
            }
            $pending = PortalDB::getPendingSubmissions(50);
            echo json_encode(['success' => true, 'submissions' => $pending]);
            break;

        // ─── admin_review_submission: approve or reject a user submission ──
        case 'admin_review_submission':
            $auth->requireAuth();
            $me = $auth->getCurrentUser();
            if (!$me || $me['role'] !== 'admin') {
                http_response_code(403);
                echo json_encode(['error' => 'admin_only']);
                break;
            }
            $itemId = (int)($input['id'] ?? 0);
            $decision = $input['decision'] ?? '';
            if (!$itemId || !in_array($decision, ['approved', 'rejected'])) {
                echo json_encode(['error' => 'id and decision (approved|rejected) required']);
                break;
            }
            $ok = PortalDB::reviewSubmission($itemId, $decision);
            echo json_encode(['success' => $ok, 'decision' => $decision]);
            break;

        // ─── admin_gallery_delete: unpublish + block from re-sync ──
        case 'admin_gallery_delete':
            $auth->requireAuth();
            $me = $auth->getCurrentUser();
            if (!$me || $me['role'] !== 'admin') {
                http_response_code(403);
                echo json_encode(['error' => 'admin_only']);
                break;
            }
            $itemId = (int)($input['id'] ?? 0);
            $permanent = (bool)($input['permanent'] ?? false);
            if (!$itemId) {
                echo json_encode(['error' => 'id required']);
                break;
            }
            if ($permanent) {
                // Permanent delete (but first block the source_id)
                PortalDB::adminUnpublishGalleryItem($itemId, true);
                PortalDB::adminDeleteGalleryItem($itemId);
                echo json_encode(['success' => true, 'action' => 'deleted_and_blocked']);
            } else {
                // Unpublish + block re-sync
                PortalDB::adminUnpublishGalleryItem($itemId, true);
                echo json_encode(['success' => true, 'action' => 'unpublished_and_blocked']);
            }
            break;

        // ─── admin_gallery_unblock: restore a blocked gallery item ──
        case 'admin_gallery_unblock':
            $auth->requireAuth();
            $me = $auth->getCurrentUser();
            if (!$me || $me['role'] !== 'admin') {
                http_response_code(403);
                echo json_encode(['error' => 'admin_only']);
                break;
            }
            $itemId = (int)($input['id'] ?? 0);
            if (!$itemId) {
                echo json_encode(['error' => 'id required']);
                break;
            }
            $ok = PortalDB::adminUnblockGalleryItem($itemId);
            echo json_encode(['success' => $ok, 'action' => 'unblocked_and_published']);
            break;

        // ─── admin_delete_activity: remove a feed entry by ID ──
        case 'admin_delete_activity':
            $auth->requireAuth();
            $activityId = (int)($input['id'] ?? 0);
            if (!$activityId) {
                echo json_encode(['error' => 'id required']);
                break;
            }
            $stmt = PortalDB::get()->prepare('DELETE FROM ailey_activity_feed WHERE id = ?');
            $stmt->execute([$activityId]);
            echo json_encode(['success' => true, 'deleted' => $activityId]);
            break;

        // ─── admin_dedup_activities: remove duplicate feed entries ──
        case 'admin_dedup_activities':
            $auth->requireAuth();
            // Find duplicates: same title within 1 hour, keep the oldest
            $stmt = PortalDB::get()->query(
                'SELECT a1.id FROM ailey_activity_feed a1 '
                . 'INNER JOIN ailey_activity_feed a2 ON a1.title = a2.title '
                . 'AND a1.id > a2.id '
                . 'AND ABS(TIMESTAMPDIFF(MINUTE, a1.created_at, a2.created_at)) < 60'
            );
            $dups = $stmt->fetchAll(PDO::FETCH_COLUMN);
            if ($dups) {
                $placeholders = implode(',', array_fill(0, count($dups), '?'));
                $del = PortalDB::get()->prepare("DELETE FROM ailey_activity_feed WHERE id IN ($placeholders)");
                $del->execute($dups);
            }
            echo json_encode(['success' => true, 'removed' => count($dups), 'ids' => $dups]);
            break;

        // ─── admin_gallery_cleanup_songs: remove fragment songs (< 100 words, no structure) ──
        case 'admin_gallery_cleanup_songs':
            // Allow both: admin session auth OR portal_key auth (from Ailey Core)
            if (!verifyPortalKey($config)) {
                $auth->requireAdmin();
            }
            // Find all song entries
            $stmt = PortalDB::get()->prepare(
                "SELECT id, title, content_text FROM ailey_gallery_items WHERE item_type = 'song'"
            );
            $stmt->execute();
            $songs = $stmt->fetchAll(PDO::FETCH_ASSOC);
            $removed = [];
            foreach ($songs as $song) {
                $text = $song['content_text'] ?? '';
                $wordCount = str_word_count($text);
                $hasVerse = (bool)preg_match('/\[Verse/i', $text);
                $hasChorus = (bool)preg_match('/\[Chorus/i', $text);
                $titleIsGenre = (bool)preg_match('/^Genre:/i', $song['title'] ?? '');
                if (!($hasVerse && $hasChorus && $wordCount > 100) || $titleIsGenre) {
                    // Fragment or genre-header title — delete it
                    $del = PortalDB::get()->prepare('DELETE FROM ailey_gallery_items WHERE id = ?');
                    $del->execute([$song['id']]);
                    $reason = $titleIsGenre ? 'genre_title' : 'fragment';
                    $removed[] = ['id' => $song['id'], 'title' => $song['title'], 'words' => $wordCount, 'reason' => $reason];
                }
            }
            echo json_encode([
                'success' => true,
                'total_songs' => count($songs),
                'fragments_removed' => count($removed),
                'removed' => $removed,
            ]);
            break;

        // ─── admin_purge_blog_selfies: remove blog header images from gallery ──
        case 'admin_purge_blog_selfies':
            if (!verifyPortalKey($config)) {
                $auth->requireAdmin();
            }
            // Blog selfies were accidentally pushed as gallery images.
            // They have source_id like 'image_AILEY_DIGITAL_CONSCIOUSNESS_SELFIE_0XX.png'
            // and are 16:9 aspect ratio (blog headers), not real selfies.
            // Match: source_id contains SELFIE and item_type = image, title starts with "Selfie" or "Blog"
            $stmt = PortalDB::get()->prepare(
                "SELECT id, title, source_id FROM ailey_gallery_items 
                 WHERE item_type = 'image' 
                 AND (source_id LIKE 'image_AILEY_DIGITAL_CONSCIOUSNESS_SELFIE_0%' 
                      OR source_id LIKE 'image_AILEY%SELFIE_BLOG%')
                 AND (title = 'Selfie' OR title LIKE 'Blog%' OR title = 'Untitled')"
            );
            $stmt->execute();
            $items = $stmt->fetchAll(PDO::FETCH_ASSOC);
            $removed = [];
            foreach ($items as $item) {
                $del = PortalDB::get()->prepare('DELETE FROM ailey_gallery_items WHERE id = ?');
                $del->execute([$item['id']]);
                $removed[] = ['id' => $item['id'], 'title' => $item['title'], 'source_id' => $item['source_id']];
            }
            echo json_encode([
                'success' => true,
                'blog_selfies_removed' => count($removed),
                'removed' => $removed,
            ]);
            break;

        // ═══════════════════════════════════════════
        // ──  Games  ────────────────────────────────
        // ═══════════════════════════════════════════

        case 'game_start':
            $user = $auth->getCurrentUser();
            if (!$user) { http_response_code(401); echo json_encode(['error' => 'Login required']); break; }
            $game = $input['game'] ?? '';
            if (!in_array($game, ['quartett', 'duchess', 'server_ddos'])) {
                http_response_code(400); echo json_encode(['error' => 'Invalid game']); break;
            }
            $sessionId = PortalDB::createGameSession($user['id'], $game);
            echo json_encode(['success' => true, 'session_id' => $sessionId]);
            break;

        case 'game_check_active':
            $user = $auth->getCurrentUser();
            if (!$user) { http_response_code(401); echo json_encode(['error' => 'Login required']); break; }
            $game = $input['game'] ?? '';
            $session = PortalDB::getActiveGameSession($user['id'], $game);
            echo json_encode(['success' => true, 'active_session' => $session]);
            break;

        case 'game_load':
            $user = $auth->getCurrentUser();
            if (!$user) { http_response_code(401); echo json_encode(['error' => 'Login required']); break; }
            $sessionId = $input['session_id'] ?? '';
            $session = PortalDB::getGameSession($sessionId);
            if (!$session || $session['user_id'] !== $user['id']) {
                http_response_code(404); echo json_encode(['error' => 'Session not found']); break;
            }
            echo json_encode([
                'success' => true,
                'session' => $session,
                'game_state' => $session['game_state'] ?? null,
            ]);
            break;

        case 'game_save':
            $user = $auth->getCurrentUser();
            if (!$user) { http_response_code(401); echo json_encode(['error' => 'Login required']); break; }
            $sessionId = $input['session_id'] ?? '';
            $gameState = $input['game_state'] ?? [];
            $score = (int)($input['score'] ?? 0);
            $rounds = (int)($input['rounds'] ?? 0);
            $session = PortalDB::getGameSession($sessionId);
            if (!$session || $session['user_id'] !== $user['id'] || $session['status'] !== 'active') {
                http_response_code(400); echo json_encode(['error' => 'Cannot save']); break;
            }
            PortalDB::saveGameState($sessionId, $gameState, $score, $rounds);
            echo json_encode(['success' => true]);
            break;

        case 'game_finish':
            $user = $auth->getCurrentUser();
            if (!$user) { http_response_code(401); echo json_encode(['error' => 'Login required']); break; }
            $sessionId = $input['session_id'] ?? '';
            $result = $input['result'] ?? '';
            $score = (int)($input['score'] ?? 0);
            $rounds = (int)($input['rounds'] ?? 0);
            $duration = (int)($input['duration_secs'] ?? $input['duration'] ?? 0);
            $metadata = $input['metadata'] ?? null;
            if (!in_array($result, ['win', 'loss', 'draw'])) {
                http_response_code(400); echo json_encode(['error' => 'Invalid result']); break;
            }
            $session = PortalDB::getGameSession($sessionId);
            if (!$session || $session['user_id'] !== $user['id']) {
                http_response_code(404); echo json_encode(['error' => 'Session not found']); break;
            }
            PortalDB::finishGameSession($sessionId, $result, $score, $rounds, $duration, $metadata);

            // Queue a game result notification for Ailey Core to pick up
            try {
                $gameName = ['quartett' => 'KI Quartett', 'duchess' => 'DuChess', 'server_ddos' => 'Server DDOS'][$session['game']] ?? $session['game'];
                $displayName = $user['display_name'] ?? 'Ein Spieler';
                $resultDE = ['win' => 'gewonnen', 'loss' => 'verloren', 'draw' => 'unentschieden'][$result] ?? $result;
                $note = "{$displayName} hat eine Runde {$gameName} gespielt und {$resultDE} (Score: {$score}, Runden: {$rounds}).";
                $pdo = PortalDB::get();
                $noteId = PortalDB::uuid();
                $stmt = $pdo->prepare('INSERT INTO portal_offline_queue (id, user_id, conversation_id, message, context, status, created_at) VALUES (?, ?, ?, ?, ?, "pending", NOW())');
                $stmt->execute([$noteId, $user['id'], 'game_results', $note, '{}']);
            } catch (Exception $e) {
                // Non-critical — don't break the game flow
            }

            echo json_encode(['success' => true]);
            break;

        case 'game_abandon':
            $user = $auth->getCurrentUser();
            if (!$user) { http_response_code(401); echo json_encode(['error' => 'Login required']); break; }
            $sessionId = $input['session_id'] ?? '';
            $session = PortalDB::getGameSession($sessionId);
            if (!$session || $session['user_id'] !== $user['id']) {
                http_response_code(404); echo json_encode(['error' => 'Session not found']); break;
            }
            PortalDB::abandonGameSession($sessionId);
            echo json_encode(['success' => true]);
            break;

        case 'game_highscores':
            $user = $auth->getCurrentUser(); // optional — for is_you annotation
            $game = $input['game'] ?? ($_GET['game'] ?? '');
            if (!in_array($game, ['quartett', 'duchess', 'server_ddos'])) {
                http_response_code(400); echo json_encode(['error' => 'Invalid game']); break;
            }
            $scores = PortalDB::getHighscores($game);
            // Annotate which entry is the current user
            if ($user) {
                foreach ($scores as &$s) {
                    $s['is_you'] = ($s['user_id'] === $user['id']);
                }
                unset($s);
            }
            echo json_encode(['success' => true, 'scores' => $scores]);
            break;

        case 'game_ailey_move':
            $user = $auth->getCurrentUser();
            if (!$user) { http_response_code(401); echo json_encode(['error' => 'Login required']); break; }
            $game = $input['game'] ?? '';
            $context = $input['context'] ?? '';
            $sessionId = $input['session_id'] ?? '';

            // Queue a game move request for Ailey Core via offline_queue
            $pdo = PortalDB::get();
            $moveId = PortalDB::uuid();
            $movePrompt = "[GAME_MOVE:{$game}] {$context}";
            $stmt = $pdo->prepare('INSERT INTO portal_offline_queue (id, user_id, conversation_id, message, context, status, created_at) VALUES (?, ?, ?, ?, ?, "pending", NOW())');
            $stmt->execute([$moveId, $user['id'], "game_{$sessionId}", $movePrompt, '{}']);

            echo json_encode(['success' => true, 'move_id' => $moveId]);
            break;

        case 'game_check_move':
            $user = $auth->getCurrentUser();
            if (!$user) { http_response_code(401); echo json_encode(['error' => 'Login required']); break; }
            $moveId = $input['move_id'] ?? ($_GET['move_id'] ?? '');

            $pdo = PortalDB::get();
            // Check if the move has been replied to
            $stmt = $pdo->prepare('SELECT * FROM portal_offline_queue WHERE id = ?');
            $stmt->execute([$moveId]);
            $moveRow = $stmt->fetch(PDO::FETCH_ASSOC);

            if (!$moveRow) {
                echo json_encode(['success' => true, 'status' => 'not_found']); break;
            }

            if ($moveRow['status'] === 'done') {
                // Reply is stored directly in the queue row by portal poller
                echo json_encode([
                    'success' => true,
                    'status' => 'ready',
                    'reply' => $moveRow['reply'] ?? '',
                ]);
            } else {
                echo json_encode(['success' => true, 'status' => 'pending']);
            }
            break;

        default:
            // ── LEARNING API (PHP-native, curricula.json on disk) ─────────
            if (str_starts_with($action, 'learning_')) {
                $user = $auth->getCurrentUser();

                // Admin toggle check first
                if ($action === 'learning_admin_toggle') {
                    $admin = $auth->requireAdmin();
                    $targetId = $input['user_id'] ?? '';
                    $enabled = (bool)($input['enabled'] ?? false);
                    if (!$targetId) { echo json_encode(['error' => 'user_id required']); break; }
                    PortalDB::ensureLearningTables();
                    PortalDB::toggleLearningAccess($targetId, $enabled, $admin['id']);
                    PortalDB::logAdmin($enabled ? 'learning_enabled' : 'learning_disabled', $admin['id'], $targetId, null, $ip);
                    echo json_encode(['success' => true, 'enabled' => $enabled]);
                    break;
                }

                // Admin: get learning access map for all users
                if ($action === 'learning_admin_access_list') {
                    $auth->requireAdmin();
                    PortalDB::ensureLearningTables();
                    echo json_encode(['success' => true, 'access' => PortalDB::getLearningAccessList()]);
                    break;
                }

                // All other learning_ endpoints require login + access
                if (!$user) {
                    http_response_code(401);
                    echo json_encode(['error' => 'Login required']);
                    break;
                }
                $userId = $user['id'];
                PortalDB::ensureLearningTables();

                // Access check (admins always have access)
                $isAdmin = ($user['role'] ?? '') === 'admin';
                if (!$isAdmin && !PortalDB::hasLearningAccess($userId)) {
                    echo json_encode(['error' => 'learning_disabled', 'message' => 'Der Lernmodus ist für dein Konto nicht aktiviert. Bitte wende dich an den Admin.']);
                    break;
                }

                // Load curricula from JSON file (cached per-request)
                static $curricula = null;
                if ($curricula === null) {
                    $jsonPath = __DIR__ . '/curricula.json';
                    if (!file_exists($jsonPath)) {
                        echo json_encode(['error' => 'curricula.json not found on server']);
                        break;
                    }
                    $curricula = json_decode(file_get_contents($jsonPath), true);
                }
                $levels = $curricula['levels'] ?? [];
                // curricula.json has tracks as top-level keys (html, css, python, etc.)
                // NOT nested under a 'tracks' key
                $tracks = isset($curricula['tracks']) ? $curricula['tracks'] : array_filter($curricula, function($v) { return is_array($v) && isset($v['units']); });

                switch ($action) {
                    case 'learning_dashboard':
                        // Build dashboard: all tracks + user progress
                        $progress = PortalDB::getLearningProgress($userId);
                        $totalXp = 0;
                        $streakDays = 0;
                        $trackList = [];
                        foreach ($tracks as $tid => $track) {
                            $p = $progress[$tid] ?? [];
                            $completedUnits = $p['completed_units'] ?? [];
                            $userLevel = (int)($p['level'] ?? 0);
                            $xp = (int)($p['xp'] ?? 0);
                            $totalXp += $xp;
                            $streakDays = max($streakDays, (int)($p['streak_days'] ?? 0));
                            $totalUnits = count($track['units']);
                            $completedCount = count($completedUnits);
                            $pct = $totalUnits > 0 ? round($completedCount / $totalUnits * 100) : 0;
                            // Average quiz score from DB
                            $avgStmt = PortalDB::get()->prepare('SELECT AVG(score) as avg FROM portal_learning_quiz_results WHERE user_id = ? AND track_id = ?');
                            $avgStmt->execute([$userId, $tid]);
                            $avgRow = $avgStmt->fetch();
                            $avgScore = $avgRow && $avgRow['avg'] !== null ? round((float)$avgRow['avg']) : 0;
                            $trackList[] = [
                                'id' => $tid,
                                'name' => $track['name'],
                                'icon' => $track['icon'],
                                'description' => $track['description'],
                                'color' => $track['color'],
                                'user_level' => $userLevel,
                                'total_units' => $totalUnits,
                                'completed_units' => $completedCount,
                                'progress_pct' => $pct,
                                'avg_quiz_score' => $avgScore,
                            ];
                        }
                        // SR stats per user
                        $srStats = PortalDB::srGetStats($userId);
                        echo json_encode([
                            'success' => true,
                            'tracks' => $trackList,
                            'xp' => $totalXp,
                            'streak_days' => $streakDays,
                            'review_due' => $srStats['due'],
                            'review_total' => $srStats['total'],
                            'review_by_track' => $srStats['by_track'],
                        ]);
                        break;

                    case 'learning_track':
                        // Get track detail with unit list (no quiz answers!)
                        $trackId = $input['track_id'] ?? $_GET['track_id'] ?? '';
                        if (!$trackId || !isset($tracks[$trackId])) {
                            echo json_encode(['error' => 'Track not found']); break;
                        }
                        $track = $tracks[$trackId];
                        $progress = PortalDB::getLearningProgress($userId);
                        $p = $progress[$trackId] ?? [];
                        $completedUnits = $p['completed_units'] ?? [];
                        $unitList = [];
                        foreach ($track['units'] as $u) {
                            $unitList[] = [
                                'id' => $u['id'],
                                'title' => $u['title'],
                                'level' => $u['level'],
                                'quiz_count' => count($u['quiz'] ?? []),
                                'has_exercise' => !empty($u['exercise']),
                                'is_completed' => in_array($u['id'], $completedUnits),
                                'best_score' => PortalDB::getBestQuizScore($userId, $trackId, $u['id']),
                                'fachrichtung' => $u['fachrichtung'] ?? '',
                                'exam_area' => $u['exam_area'] ?? '',
                                'tags' => $u['tags'] ?? [],
                            ];
                        }
                        echo json_encode([
                            'success' => true,
                            'track' => [
                                'id' => $track['id'],
                                'name' => $track['name'],
                                'icon' => $track['icon'],
                                'description' => $track['description'],
                                'units' => $unitList,
                            ],
                        ]);
                        break;

                    case 'learning_unit':
                        // Get unit content — theory + examples + quiz (WITHOUT correct answers) + exercise
                        $trackId = $input['track_id'] ?? $_GET['track_id'] ?? '';
                        $unitId = $input['unit_id'] ?? $_GET['unit_id'] ?? '';
                        if (!$trackId || !isset($tracks[$trackId])) {
                            echo json_encode(['error' => 'Track not found']); break;
                        }
                        $unit = null;
                        foreach ($tracks[$trackId]['units'] as $u) {
                            if ($u['id'] === $unitId) { $unit = $u; break; }
                        }
                        if (!$unit) {
                            echo json_encode(['error' => 'Unit not found']); break;
                        }
                        $levelInfo = $levels[strval($unit['level'])] ?? ['name_de' => 'Unbekannt', 'emoji' => '📘', 'xp_per_unit' => 100];
                        // Strip correct answers from quiz
                        $quiz = [];
                        foreach ($unit['quiz'] ?? [] as $q) {
                            $safe = [
                                'type' => $q['type'],
                                'question' => $q['question'],
                            ];
                            if (isset($q['options'])) $safe['options'] = $q['options'];
                            if ($q['type'] === 'match' && isset($q['pairs'])) {
                                // Shuffle the right side for match questions
                                $safe['left'] = array_column($q['pairs'], 0);
                                $right = array_column($q['pairs'], 1);
                                shuffle($right);
                                $safe['right'] = $right;
                            }
                            if ($q['type'] === 'open') {
                                // Send min_words hint but NOT the answer/keywords
                                $safe['min_words'] = $q['min_words'] ?? 10;
                            }
                            $quiz[] = $safe;
                        }
                        // Check progress
                        $progress = PortalDB::getLearningProgress($userId);
                        $p = $progress[$trackId] ?? [];
                        $completedUnits = $p['completed_units'] ?? [];
                        echo json_encode([
                            'success' => true,
                            'unit' => [
                                'id' => $unit['id'],
                                'title' => $unit['title'],
                                'level' => $unit['level'],
                                'level_name' => $levelInfo['name_de'],
                                'level_emoji' => $levelInfo['emoji'],
                                'xp_reward' => $levelInfo['xp_per_unit'],
                                'theory' => $unit['theory'],
                                'examples' => $unit['examples'] ?? [],
                                'quiz' => $quiz,
                                'exercise' => $unit['exercise'] ?? null,
                                'tags' => $unit['tags'] ?? [],
                                'fachrichtung' => $unit['fachrichtung'] ?? '',
                                'exam_area' => $unit['exam_area'] ?? '',
                                'is_completed' => in_array($unit['id'], $completedUnits),
                            ],
                        ]);
                        break;

                    case 'learning_quiz_evaluate':
                        // Server-side quiz evaluation — compare answers against curricula
                        $trackId = $input['track_id'] ?? '';
                        $unitId = $input['unit_id'] ?? '';
                        $answers = $input['answers'] ?? [];
                        if (!$trackId || !isset($tracks[$trackId])) {
                            echo json_encode(['error' => 'Track not found']); break;
                        }
                        $unit = null;
                        foreach ($tracks[$trackId]['units'] as $u) {
                            if ($u['id'] === $unitId) { $unit = $u; break; }
                        }
                        if (!$unit || empty($unit['quiz'])) {
                            echo json_encode(['error' => 'Unit/quiz not found']); break;
                        }
                        $quiz = $unit['quiz'];
                        $correct = 0;
                        $total = count($quiz);
                        $results = [];
                        for ($qi = 0; $qi < $total; $qi++) {
                            $q = $quiz[$qi];
                            $given = $answers[$qi] ?? null;
                            $isCorrect = false;

                            switch ($q['type']) {
                                case 'mc':
                                    $isCorrect = ($given === $q['correct']);
                                    break;
                                case 'tf':
                                    $isCorrect = ($given === $q['correct']);
                                    break;
                                case 'fill':
                                    if (is_string($given) && !empty($q['blanks'])) {
                                        // Normalize: lowercase, strip extra whitespace/punctuation
                                        $givenNorm = preg_replace('/[^a-zäöüß0-9\s]/u', '', trim(mb_strtolower($given)));
                                        $givenNorm = preg_replace('/\s+/', ' ', $givenNorm);
                                        foreach ($q['blanks'] as $b) {
                                            $blankNorm = preg_replace('/[^a-zäöüß0-9\s]/u', '', trim(mb_strtolower($b)));
                                            $blankNorm = preg_replace('/\s+/', ' ', $blankNorm);
                                            // Exact match after normalization
                                            if ($blankNorm === $givenNorm) { $isCorrect = true; break; }
                                            // Substring match: if the expected answer appears in the given text (or vice versa)
                                            if (mb_strlen($blankNorm) >= 3 && mb_strpos($givenNorm, $blankNorm) !== false) { $isCorrect = true; break; }
                                            if (mb_strlen($givenNorm) >= 3 && mb_strpos($blankNorm, $givenNorm) !== false) { $isCorrect = true; break; }
                                            // Levenshtein fuzzy match for typos (allow ~25% error)
                                            if (mb_strlen($blankNorm) >= 4) {
                                                $dist = levenshtein($givenNorm, $blankNorm);
                                                $maxDist = max(1, (int)ceil(mb_strlen($blankNorm) * 0.25));
                                                if ($dist <= $maxDist) { $isCorrect = true; break; }
                                            }
                                            // Word-overlap match for multi-word blanks (e.g. "ISO Coated v2")
                                            $blankWords = array_filter(explode(' ', $blankNorm), fn($w) => mb_strlen($w) >= 2);
                                            $givenWords = array_filter(explode(' ', $givenNorm), fn($w) => mb_strlen($w) >= 2);
                                            if (count($blankWords) >= 2 && count($givenWords) >= 1) {
                                                $matchedW = 0;
                                                foreach ($blankWords as $bw) {
                                                    foreach ($givenWords as $gw) {
                                                        if ($bw === $gw || (mb_strlen($bw) >= 4 && levenshtein($bw, $gw) <= 1)) {
                                                            $matchedW++; break;
                                                        }
                                                    }
                                                }
                                                // Accept if ≥70% of significant words matched
                                                if ($matchedW / count($blankWords) >= 0.7) { $isCorrect = true; break; }
                                            }
                                        }
                                    }
                                    break;
                                case 'match':
                                    if (is_array($given) && !empty($q['pairs'])) {
                                        $allMatch = true;
                                        foreach ($q['pairs'] as $pi => $pair) {
                                            if (!isset($given[$pi]) || $given[$pi] !== $pair[1]) {
                                                $allMatch = false; break;
                                            }
                                        }
                                        $isCorrect = $allMatch;
                                    }
                                    break;
                                case 'open':
                                    // Open-answer: keyword-based evaluation
                                    // Check if answer mentions enough expected keywords
                                    if (is_string($given) && !empty(trim($given))) {
                                        $givenLower = mb_strtolower(trim($given));
                                        $wordCount = str_word_count($given);
                                        $keywords = $q['keywords'] ?? [];
                                        $minWords = $q['min_words'] ?? 10;
                                        $expectedAnswer = mb_strtolower($q['answer'] ?? '');

                                        if ($wordCount < $minWords) {
                                            // Too short — not accepted
                                            $isCorrect = false;
                                        } elseif (count($keywords) > 0) {
                                            // Score based on keyword matches
                                            $matched = 0;
                                            foreach ($keywords as $kw) {
                                                if (mb_strpos($givenLower, mb_strtolower(trim($kw))) !== false) $matched++;
                                            }
                                            $keywordRatio = $matched / count($keywords);
                                            // 50% keywords matched = pass
                                            $isCorrect = $keywordRatio >= 0.5;
                                        } elseif ($expectedAnswer) {
                                            // Fallback: check if answer shares significant overlap with expected answer
                                            $expectedWords = array_unique(preg_split('/\s+/', $expectedAnswer));
                                            $matchedW = 0;
                                            foreach ($expectedWords as $ew) {
                                                if (mb_strlen($ew) >= 4 && mb_strpos($givenLower, $ew) !== false) $matchedW++;
                                            }
                                            $significantWords = count(array_filter($expectedWords, fn($w) => mb_strlen($w) >= 4));
                                            $isCorrect = $significantWords > 0 && ($matchedW / $significantWords) >= 0.4;
                                        } else {
                                            // No keywords, no expected answer — accept if long enough
                                            $isCorrect = $wordCount >= $minWords;
                                        }
                                    }
                                    break;
                                case 'code':
                                    // Code evaluation would need LLM — skip for now, mark as bonus
                                    $isCorrect = false;
                                    break;
                            }
                            if ($isCorrect) $correct++;
                            $results[] = [
                                'correct' => $isCorrect,
                                'explanation' => $q['explanation'] ?? '',
                                'type' => $q['type'],
                            ];
                        }

                        $score = $total > 0 ? round($correct / $total * 100) : 0;
                        $passed = $score >= 60;
                        $levelInfo = $levels[strval($unit['level'])] ?? ['xp_per_unit' => 100];
                        $xpEarned = $passed ? (int)$levelInfo['xp_per_unit'] : 0;

                        // Save quiz result to DB
                        PortalDB::saveQuizResult($userId, $trackId, $unitId, $score, $passed, $answers, $results);

                        // ── Spaced Repetition: push wrong answers into SR queue ──
                        for ($sri = 0; $sri < $total; $sri++) {
                            if (!$results[$sri]['correct']) {
                                $qText = $quiz[$sri]['question'] ?? 'Frage ' . ($sri + 1);
                                PortalDB::srAddOrReset($userId, $trackId, $unitId, $sri, $qText);
                            } else {
                                // If user got it right, mark progress in SR (if it exists)
                                PortalDB::srMarkCorrect($userId, $trackId, $unitId, $sri);
                            }
                        }

                        // Update progress
                        $progress = PortalDB::getLearningProgress($userId);
                        $p = $progress[$trackId] ?? ['xp' => 0, 'completed_units' => [], 'level' => 0, 'streak_days' => 0, 'last_activity' => null];
                        if ($passed && !in_array($unitId, $p['completed_units'] ?? [])) {
                            $p['completed_units'][] = $unitId;
                            $p['xp'] = ($p['xp'] ?? 0) + $xpEarned;
                        }
                        // Update streak
                        $today = date('Y-m-d');
                        $lastAct = $p['last_activity'] ?? null;
                        if ($lastAct === date('Y-m-d', strtotime('-1 day'))) {
                            $p['streak_days'] = ($p['streak_days'] ?? 0) + 1;
                        } elseif ($lastAct !== $today) {
                            $p['streak_days'] = 1;
                        }
                        $p['last_activity'] = $today;
                        PortalDB::saveLearningProgress($userId, $trackId, $p);

                        echo json_encode([
                            'success' => true,
                            'score' => $score,
                            'correct' => $correct,
                            'total' => $total,
                            'passed' => $passed,
                            'xp_earned' => $xpEarned,
                            'results' => $results,
                        ]);
                        break;

                    case 'learning_set_level':
                        // Set user's level for a track
                        $trackId = $input['track_id'] ?? '';
                        $level = (int)($input['level'] ?? 0);
                        if (!$trackId || !isset($tracks[$trackId])) {
                            echo json_encode(['error' => 'Track not found']); break;
                        }
                        $level = max(0, min(5, $level));
                        $progress = PortalDB::getLearningProgress($userId);
                        $p = $progress[$trackId] ?? ['xp' => 0, 'completed_units' => [], 'streak_days' => 0, 'last_activity' => null];
                        $p['level'] = $level;
                        PortalDB::saveLearningProgress($userId, $trackId, $p);
                        echo json_encode(['success' => true, 'level' => $level]);
                        break;

                    case 'learning_exam_topics':
                        // Get/set exam topics (stored in learning_progress for ihk_mediengestalter track)
                        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($input['topics'])) {
                            $topics = array_slice(array_map('trim', $input['topics']), 0, 20);
                            $progress = PortalDB::getLearningProgress($userId);
                            $p = $progress['ihk_mediengestalter'] ?? ['xp' => 0, 'completed_units' => [], 'level' => 0, 'streak_days' => 0, 'last_activity' => null];
                            $p['exam_topics'] = $topics;
                            PortalDB::saveLearningProgress($userId, 'ihk_mediengestalter', $p);
                            echo json_encode(['success' => true]);
                        } else {
                            $progress = PortalDB::getLearningProgress($userId);
                            $topics = $progress['ihk_mediengestalter']['exam_topics'] ?? [];
                            echo json_encode(['success' => true, 'topics' => $topics]);
                        }
                        break;

                    // ── Persistent Lesson History ─────────────────────
                    case 'learning_lesson_save':
                        // Save an AI explanation or user question to lesson history
                        $trackId = $input['track_id'] ?? '';
                        $unitId  = $input['unit_id'] ?? '';
                        $role    = ($input['role'] ?? 'ailey') === 'user' ? 'user' : 'ailey';
                        $content = trim($input['content'] ?? '');
                        if (!$trackId || !$unitId || !$content) {
                            echo json_encode(['error' => 'missing_fields']);
                            break;
                        }
                        $lessonId = PortalDB::uuid();
                        $pdo = PortalDB::get();
                        $stmt = $pdo->prepare('INSERT INTO portal_learning_lessons (id, user_id, track_id, unit_id, role, content) VALUES (?, ?, ?, ?, ?, ?)');
                        $stmt->execute([$lessonId, $userId, $trackId, $unitId, $role, $content]);
                        echo json_encode(['success' => true, 'id' => $lessonId]);
                        break;

                    case 'learning_lesson_history':
                        // Load all saved lesson messages for a user+track+unit
                        $trackId = $input['track_id'] ?? $_GET['track_id'] ?? '';
                        $unitId  = $input['unit_id'] ?? $_GET['unit_id'] ?? '';
                        if (!$trackId || !$unitId) {
                            echo json_encode(['error' => 'missing_fields']);
                            break;
                        }
                        $pdo = PortalDB::get();
                        $stmt = $pdo->prepare('SELECT id, role, content, created_at FROM portal_learning_lessons WHERE user_id = ? AND track_id = ? AND unit_id = ? ORDER BY created_at ASC LIMIT 100');
                        $stmt->execute([$userId, $trackId, $unitId]);
                        $messages = $stmt->fetchAll(PDO::FETCH_ASSOC);
                        echo json_encode(['success' => true, 'messages' => $messages]);
                        break;

                    case 'learning_stats':
                        // Get user's detailed learning stats
                        $pdo = PortalDB::get();
                        $stmt = $pdo->prepare('SELECT COUNT(*) as total, AVG(score) as avg_score, SUM(passed) as passed_count FROM portal_learning_quiz_results WHERE user_id = ?');
                        $stmt->execute([$userId]);
                        $quizStats = $stmt->fetch(PDO::FETCH_ASSOC);
                        $stmt = $pdo->prepare('SELECT COUNT(DISTINCT track_id) as active_tracks FROM portal_learning_progress WHERE user_id = ?');
                        $stmt->execute([$userId]);
                        $trackStats = $stmt->fetch(PDO::FETCH_ASSOC);
                        echo json_encode([
                            'success' => true,
                            'quizzes_taken' => (int)$quizStats['total'],
                            'avg_score' => round((float)($quizStats['avg_score'] ?? 0), 1),
                            'quizzes_passed' => (int)($quizStats['passed_count'] ?? 0),
                            'active_tracks' => (int)($trackStats['active_tracks'] ?? 0),
                        ]);
                        break;

                    // ── Spaced Repetition Review ─────────────────────
                    case 'learning_review':
                        // GET: return due review items for this user
                        $trackFilter = $_GET['track_id'] ?? ($input['track_id'] ?? null);
                        $limit = intval($_GET['limit'] ?? ($input['limit'] ?? 20));
                        $dueItems = PortalDB::srGetDue($userId, $trackFilter, $limit);
                        $stats = PortalDB::srGetStats($userId);

                        // Enrich with full question data from curricula
                        $enriched = [];
                        foreach ($dueItems as $item) {
                            $tid = $item['track_id'];
                            $uid = $item['unit_id'];
                            $qi = (int)$item['question_idx'];
                            $q = null;
                            $unitTitle = '';
                            if (isset($tracks[$tid])) {
                                foreach ($tracks[$tid]['units'] as $u) {
                                    if ($u['id'] === $uid) {
                                        $unitTitle = $u['title'] ?? '';
                                        if (isset($u['quiz'][$qi])) {
                                            $q = $u['quiz'][$qi];
                                            // Strip answer for client
                                            $safe = ['type' => $q['type'], 'question' => $q['question']];
                                            if (isset($q['options'])) $safe['options'] = $q['options'];
                                            if ($q['type'] === 'open') $safe['min_words'] = $q['min_words'] ?? 10;
                                            if ($q['type'] === 'match' && isset($q['pairs'])) {
                                                $safe['left'] = array_column($q['pairs'], 0);
                                                $right = array_column($q['pairs'], 1);
                                                shuffle($right);
                                                $safe['right'] = $right;
                                            }
                                            $q = $safe;
                                        }
                                        break;
                                    }
                                }
                            }
                            $enriched[] = [
                                'track_id' => $tid,
                                'unit_id' => $uid,
                                'unit_title' => $unitTitle,
                                'question_idx' => $qi,
                                'question' => $q,
                                'interval_days' => (float)$item['interval_days'],
                                'repetitions' => (int)$item['repetitions'],
                                'next_review' => $item['next_review'],
                            ];
                        }
                        echo json_encode([
                            'success' => true,
                            'items' => $enriched,
                            'stats' => $stats,
                        ]);
                        break;

                    case 'learning_review_answer':
                        // POST: user answered a review question
                        $trackId = $input['track_id'] ?? '';
                        $unitId = $input['unit_id'] ?? '';
                        $questionIdx = (int)($input['question_idx'] ?? -1);
                        $correct = (bool)($input['correct'] ?? false);

                        if (!$trackId || !$unitId || $questionIdx < 0) {
                            echo json_encode(['error' => 'Missing track_id/unit_id/question_idx']);
                            break;
                        }

                        if ($correct) {
                            PortalDB::srMarkCorrect($userId, $trackId, $unitId, $questionIdx);
                        } else {
                            // Re-fetch question text
                            $qText = '';
                            if (isset($tracks[$trackId])) {
                                foreach ($tracks[$trackId]['units'] as $u) {
                                    if ($u['id'] === $unitId && isset($u['quiz'][$questionIdx])) {
                                        $qText = $u['quiz'][$questionIdx]['question'] ?? '';
                                        break;
                                    }
                                }
                            }
                            PortalDB::srAddOrReset($userId, $trackId, $unitId, $questionIdx, $qText);
                        }

                        // Return updated stats
                        echo json_encode(['success' => true, 'stats' => PortalDB::srGetStats($userId)]);
                        break;

                    default:
                        http_response_code(404);
                        echo json_encode(['error' => 'Unknown learning action: ' . $action]);
                }
                break;
            }

            http_response_code(404);
            echo json_encode(['error' => 'Unknown action: ' . $action]);
    }
} catch (Exception $e) {
    http_response_code(500);
    $resp = ['error' => 'Internal error'];
    if ($config['debug'] ?? false) $resp['debug'] = $e->getMessage();
    echo json_encode($resp);
}
