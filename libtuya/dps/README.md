# DPS Discovery Engine

The DPS Discovery Engine is a comprehensive system for mapping Home Assistant device capabilities to actual TinyTuya DPS indices using intelligent heuristics and real-time device probing.

## Overview

This system solves the critical challenge of mapping abstract device capabilities (like "brightness" or "switch") to concrete DPS indices (like DPS 3 or DPS 1) that TinyTuya uses for local device control.

## Architecture

### Core Components

1. **mapping_rules.py** - Bulletproof DPS mapping heuristics
   - Category-specific mappings for 60+ device types
   - Universal patterns (DPS 1=switch, 3=brightness, 5=color)
   - Fallback logic for unknown devices
   - Confidence scoring system

2. **discovery.py** - TinyTuya DPS discovery and intelligent matching
   - Uses TinyTuya's `detect_available_dps()` method
   - Manual probing fallback when auto-detection fails
   - Intelligent capability-to-DPS matching with confidence scores
   - Handles multiple DPS ranges (1-11, 20-31, 100-111)

3. **mapper.py** - Main DPS mapping interface
   - Combines HA intelligence with TinyTuya discovery
   - Bidirectional mapping (capability ↔ DPS)
   - Persistent caching system
   - Mapping validation and quality scoring

4. ****init**.py** - Clean API interface
   - DPSMapper class as primary entry point
   - Convenience functions for common operations
   - Constants and reference data

## Key Features

### Bulletproof Heuristics

The system implements carefully researched heuristics based on Home Assistant's real-world device knowledge:

- **DPS 1**: Switch (99% universal)
- **DPS 3**: Brightness (lights)
- **DPS 5**: Color data (RGB lights)
- **DPS 4**: Color temperature (white lights)
- **DPS 2**: Work mode (most devices)

### Device Category Support

Supports all major device categories:

- **Lights**: dj, dc, dd, dsd, xdd, tgkg, tgq, etc.
- **Switches**: kg, pc, tdq
- **Climate**: kt, qn, wk, wkf
- **Fans**: fs, fsd
- **Covers**: cl
- **Sensors**: sp
- **Appliances**: jsq, kj, cs

### Intelligent Discovery

- Uses TinyTuya's built-in discovery first
- Falls back to manual probing if needed
- Probes multiple DPS ranges intelligently
- Matches expected capabilities to discovered DPS
- Validates mappings with confidence scores

### Persistent Caching

- Caches successful mappings to avoid repeated discovery
- Handles cache invalidation and updates
- Exports/imports mappings for backup/restore
- Thread-safe cache operations

## Usage Examples

### Basic Usage

```python
from libtuya.dps import DPSMapper, DeviceInfo

# Create mapper
mapper = DPSMapper()

# Define device info
device_info = DeviceInfo(
    device_id="bf1234567890abcdef",
    category="dj",  # Light category
    name="Living Room Light"
)

# Discover DPS mapping
mappings = mapper.discover_dps_mapping(
    device_info=device_info,
    expected_capabilities=["switch_led", "bright_value", "colour_data"],
    tinytuya_device=tinytuya_device
)

# Use mappings
switch_dps = mapper.get_dps_for_capability(device_info.device_id, "switch_led")
brightness_dps = mapper.get_dps_for_capability(device_info.device_id, "bright_value")
```

### Advanced Usage

```python
# Get bidirectional mapping
dps_to_cap = mapper.get_dps_to_capability_mapping(device_info.device_id)
print(f"DPS 1 controls: {dps_to_cap.get(1)}")

# Validate mapping quality
validation = mapper.validate_mapping(device_info.device_id)
print(f"Mapping valid: {validation['valid']}, Score: {validation['score']}")

# Get mapping summary
summary = mapper.get_mapping_summary(device_info.device_id)
print(f"Device has {summary['mapping_count']} mappings")
print(f"Average confidence: {summary['avg_confidence']:.2f}")
```

### Manual Mapping

```python
# Manually update a mapping
mapper.update_mapping(
    device_id="bf1234567890abcdef",
    capability="switch_led",
    dps=1,
    confidence=DPSConfidence.HIGH,
    reason="Manual verification"
)

# Export mappings for backup
mapper.export_mappings("bf1234567890abcdef", Path("device_mappings.json"))
```

## Testing

Comprehensive test coverage with mock TinyTuya devices:

```bash
# Run all DPS tests
python -m pytest tests/dps/

# Run specific test files
python -m pytest tests/dps/test_mapping_rules.py
python -m pytest tests/dps/test_discovery.py
python -m pytest tests/dps/test_mapper.py
python -m pytest tests/dps/test_init.py
```

## Integration

The DPS Discovery Engine integrates with:

- **Home Assistant Intelligence**: Uses exact HA device mappings and scaling rules
- **TinyTuya**: Leverages `detect_available_dps()` and device control methods
- **libtuya Core**: Provides DPS mappings for intelligent device control

## Error Handling

Robust error handling for:

- Device unreachable during discovery
- Discovery timeouts
- Invalid device categories
- Mapping validation failures
- Cache operation errors

## Performance

- Caches successful mappings to avoid repeated discovery
- Intelligent probing reduces discovery time
- Batch operations for multiple devices
- Configurable timeouts and retry logic

## Future Enhancements

- Machine learning for improved heuristics
- Device-specific quirk detection
- Real-time mapping updates
- Cloud-based mapping database
- Advanced analytics and reporting
