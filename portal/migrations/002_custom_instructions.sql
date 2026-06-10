-- Migration 002: Add custom_instructions column to portal_users
-- Run this on the live database before deploying

ALTER TABLE `portal_users` ADD COLUMN `custom_instructions` TEXT DEFAULT NULL AFTER `consent_ki`;
