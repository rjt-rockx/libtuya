"""
Integration test for basic libtuya flow
Tests the complete authentication -> discovery -> control flow
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from libtuya.auth import TuyaAuthenticator
from libtuya.devices import DeviceManager
from libtuya.intelligence import DeviceIntelligence
from libtuya.dps import DPSMapper
from libtuya.auth.models import AuthSession, DeviceInfo

class TestBasicFlow:
    """Test the basic libtuya workflow"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.authenticator = TuyaAuthenticator()
        self.device_manager = DeviceManager()
        self.intelligence = DeviceIntelligence()
        self.dps_mapper = DPSMapper()
        
        # Mock device info
        self.mock_device_info = DeviceInfo(
            id="bf1234567890abcdef",
            name="Test Light",
            category="dj",
            local_key="1234567890abcdef",
            ip="192.168.1.100",
            product_id="abcdef1234567890",
            product_name="Smart Light",
            online=True,
            uuid="test-uuid",
            asset_id="test-asset",
            status={"switch_led": True, "bright_value": 500, "colour_data": "ff0000"}
        )
        
        # Mock auth session
        self.mock_session = AuthSession(
            access_token="mock_access_token",
            refresh_token="mock_refresh_token",
            uid="mock_user_id",
            expire_time=int((datetime.now() + timedelta(hours=2)).timestamp() * 1000),
            t=int(datetime.now().timestamp() * 1000)
        )

    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """Test the complete authentication -> discovery -> control workflow"""
        
        # Mock QR authentication
        with patch.object(self.authenticator, 'start_qr_auth') as mock_qr:
            mock_qr.return_value = "mock_qr_data"
            
            qr_data = self.authenticator.start_qr_auth("test_user")
            assert qr_data == "mock_qr_data"
        
        # Mock authentication wait
        with patch.object(self.authenticator, 'wait_for_auth_async') as mock_wait:
            mock_wait.return_value = self.mock_session
            
            session = await self.authenticator.wait_for_auth_async()
            assert session.access_token == "mock_access_token"
        
        # Mock device discovery
        with patch.object(self.authenticator, 'get_devices_with_keys_async') as mock_discovery:
            mock_discovery.return_value = [self.mock_device_info]
            
            devices = await self.authenticator.get_devices_with_keys_async()
            assert len(devices) == 1
            assert devices[0].name == "Test Light"
        
        # Mock device creation
        with patch.object(self.device_manager, 'create_device') as mock_create:
            mock_device = Mock()
            mock_device.device_info = self.mock_device_info
            mock_device.turn_on = AsyncMock()
            mock_device.set_brightness_percentage = AsyncMock()
            mock_device.get_status = AsyncMock(return_value={"switch_led": True})
            mock_create.return_value = mock_device
            
            device = self.device_manager.create_device(
                device_info=self.mock_device_info,
                intelligence=self.intelligence,
                dps_mapper=self.dps_mapper
            )
            
            assert device.device_info.name == "Test Light"
            
            # Test device control
            await device.turn_on()
            device.turn_on.assert_called_once()
            
            await device.set_brightness_percentage(75)
            device.set_brightness_percentage.assert_called_once_with(75)
            
            status = await device.get_status()
            assert status["switch_led"] is True

    def test_device_intelligence_analysis(self):
        """Test device intelligence analysis"""
        analysis = self.intelligence.analyze_device("dj")  # Light device
        
        assert analysis.category == "dj"
        assert analysis.category_name == "Light"
        assert "switch_led" in analysis.capabilities
        assert "bright_value" in analysis.capabilities
        assert "colour_data" in analysis.capabilities

    def test_dps_mapping_rules(self):
        """Test DPS mapping rules"""
        from libtuya.dps.mapping_rules import MappingRulesManager
        
        rules_manager = MappingRulesManager()
        
        # Test light device mapping
        mapping = rules_manager.get_expected_mapping("dj")
        assert mapping["switch_led"] == 1  # DPS 1 = switch
        assert mapping["bright_value"] == 3  # DPS 3 = brightness
        assert mapping["colour_data"] == 5  # DPS 5 = color

    def test_value_scaling(self):
        """Test value scaling using device intelligence"""
        # Test brightness scaling
        scaled = self.intelligence.scale_value("bright_value", 75, "dj")
        assert isinstance(scaled, int)
        assert 0 <= scaled <= 1000  # Common brightness range
        
        # Test color conversion
        rgb_color = self.intelligence.convert_color_data(255, 0, 0, "rgb")
        assert rgb_color is not None

    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test error recovery mechanisms"""
        from libtuya.recovery import RecoveryManager
        from libtuya.recovery.exceptions import DeviceConnectionError
        
        recovery = RecoveryManager()
        
        # Mock a device connection error
        mock_device = Mock()
        mock_device.device_info = self.mock_device_info
        
        error = DeviceConnectionError("Connection failed", device_id="test_device")
        
        # Test that recovery manager handles the error gracefully
        with patch.object(recovery, 'recover_device_connection') as mock_recover:
            mock_recover.return_value = True
            
            result = recovery.recover_device_connection(error, mock_device)
            assert result is True

    def test_system_health_check(self):
        """Test system health diagnostics"""
        from libtuya.recovery.diagnostics import SystemDiagnostics
        
        diagnostics = SystemDiagnostics()
        
        # Test basic health check
        health = diagnostics.check_system_health()
        assert "python_version" in health
        assert "dependencies" in health
        assert "memory_usage" in health

    @pytest.mark.asyncio
    async def test_cli_integration(self):
        """Test CLI integration with core components"""
        from libtuya.cli import TuyaCLI
        
        cli = TuyaCLI()
        
        # Test that CLI initializes all components
        assert cli.authenticator is not None
        assert cli.device_manager is not None
        assert cli.intelligence is not None
        assert cli.dps_mapper is not None
        assert cli.recovery is not None

    def test_package_structure(self):
        """Test that all main package components are importable"""
        # Test main exports
        from libtuya import TuyaAuthenticator, DeviceManager
        from libtuya.intelligence import DeviceIntelligence
        from libtuya.dps import DPSMapper
        from libtuya.recovery import RecoveryManager
        
        # Test that all components can be instantiated
        auth = TuyaAuthenticator()
        manager = DeviceManager()
        intelligence = DeviceIntelligence()
        dps_mapper = DPSMapper()
        recovery = RecoveryManager()
        
        assert auth is not None
        assert manager is not None
        assert intelligence is not None
        assert dps_mapper is not None
        assert recovery is not None

    def test_configuration_validation(self):
        """Test configuration and setup validation"""
        # Test that required data files exist
        import os
        base_path = os.path.join(os.path.dirname(__file__), "..", "..", "intelligence")
        
        assert os.path.exists(os.path.join(base_path, "dpcodes.json"))
        assert os.path.exists(os.path.join(base_path, "device_mappings.json"))
        assert os.path.exists(os.path.join(base_path, "scaling_rules.json"))
        assert os.path.exists(os.path.join(base_path, "quirks.json"))

if __name__ == "__main__":
    pytest.main([__file__, "-v"])