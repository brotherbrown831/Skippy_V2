-- Migration 003: Add Home Assistant areas and devices tables
-- Date: Feb 16, 2026
-- Purpose: Support area-based and device-based control instead of entity-only interaction

-- Home Assistant Areas (rooms) with user-defined aliases
CREATE TABLE IF NOT EXISTS ha_areas (
    area_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    icon TEXT,
    aliases JSONB DEFAULT '[]'::jsonb,  -- User-defined aliases like ["office", "workspace"]
    entity_count INT DEFAULT 0,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    last_synced TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ha_areas_user ON ha_areas(user_id);
CREATE INDEX IF NOT EXISTS idx_ha_areas_aliases ON ha_areas USING gin(aliases);
CREATE INDEX IF NOT EXISTS idx_ha_areas_name ON ha_areas(user_id, name);

COMMENT ON TABLE ha_areas IS 'Home Assistant areas (rooms) with user-defined aliases for natural language control';
COMMENT ON COLUMN ha_areas.aliases IS 'User-defined aliases for area matching (e.g., ["office", "workspace"])';

-- Home Assistant Devices (multi-entity hardware) with aliases and area linkage
CREATE TABLE IF NOT EXISTS ha_devices (
    device_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    manufacturer TEXT,
    model TEXT,
    area_id TEXT REFERENCES ha_areas(area_id) ON DELETE SET NULL,
    aliases JSONB DEFAULT '[]'::jsonb,  -- User-defined aliases like ["desk lamp", "work light"]
    entity_ids TEXT[] DEFAULT '{}',     -- Array of entity_ids that belong to this device
    enabled BOOLEAN DEFAULT TRUE,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    last_synced TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ha_devices_user ON ha_devices(user_id);
CREATE INDEX IF NOT EXISTS idx_ha_devices_area ON ha_devices(area_id);
CREATE INDEX IF NOT EXISTS idx_ha_devices_aliases ON ha_devices USING gin(aliases);
CREATE INDEX IF NOT EXISTS idx_ha_devices_name ON ha_devices(user_id, name);

COMMENT ON TABLE ha_devices IS 'Home Assistant devices (multi-entity hardware) with aliases and area assignment';
COMMENT ON COLUMN ha_devices.aliases IS 'User-defined aliases for device matching (e.g., ["desk lamp", "work light"])';
COMMENT ON COLUMN ha_devices.entity_ids IS 'Array of entity_ids that belong to this device (informational, derived from HA)';

-- Enhance ha_entities table with area_id and floor_id for future area lookups
ALTER TABLE ha_entities
ADD COLUMN IF NOT EXISTS area_id TEXT,
ADD COLUMN IF NOT EXISTS floor_id TEXT;

CREATE INDEX IF NOT EXISTS idx_ha_entities_area ON ha_entities(area_id) WHERE area_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ha_entities_floor ON ha_entities(floor_id) WHERE floor_id IS NOT NULL;

COMMENT ON COLUMN ha_entities.area_id IS 'Foreign key to ha_areas.area_id for area-based queries';
COMMENT ON COLUMN ha_entities.floor_id IS 'Home Assistant floor ID for future multi-floor support';
