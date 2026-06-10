<?php
// Temporäres Hilfsskript — nach Benutzung sofort löschen!
// Aufruf: https://ask-ailey.sexngears.de/_make_hash.php?pw=DEIN_PASSWORT
$pw = $_GET['pw'] ?? '';
if (!$pw) { echo "Usage: ?pw=deinpasswort"; exit; }
$hash = password_hash($pw, PASSWORD_BCRYPT, ['cost' => 12]);
echo "Password: $pw\n\nHash:\n$hash\n\nSQL:\n";
echo "INSERT INTO portal_users (id, email, display_name, password_hash, role, status) VALUES (UUID(), 'simon@sexngears.de', 'Simon', '$hash', 'admin', 'active');";
