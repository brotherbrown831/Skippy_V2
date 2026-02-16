-- Migration 007: Remove Home Assistant device/entity management
-- Date: Feb 16, 2026
-- Purpose: Remove device control infrastructure while preserving notification capability
--
-- This migration:
-- 1. Drops HA entity management tables (ha_entities, ha_areas, ha_devices)
-- 2. Cleans up activity log entries for device control operations
-- 3. Preserves notification_sent and sms_sent activity entries

-- Drop tables (data will be lost - user accepted)
DROP TABLE IF EXISTS ha_devices CASCADE;
DROP TABLE IF EXISTS ha_areas CASCADE;
DROP TABLE IF EXISTS ha_entities CASCADE;

-- Clean up activity log entries related to HA device control
-- Keep notification_sent and sms_sent entries (these are communication tools)
DELETE FROM activity_log
WHERE activity_type IN (
    'light_turned_on', 'light_turned_off',
    'switch_turned_on', 'switch_turned_off',
    'thermostat_set',
    'door_locked', 'door_unlocked',
    'cover_opened', 'cover_closed', 'cover_position_set',
    'scene_activated',
    'ha_entities_synced'
);
