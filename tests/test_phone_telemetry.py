import asyncio
from datetime import datetime,timezone
import unittest
from unittest import mock
from phone_telemetry import normalize_snapshot,read_phone

class PhoneTelemetryTests(unittest.TestCase):
    def sample(self):
        return dict(snapshotAt=datetime.fromtimestamp(1000,timezone.utc).isoformat(),latitude=37.7,longitude=-122.4,accuracy=8,locationRecordedAt='1970-01-01T00:16:35Z',steps=2500,activityRecordedAt='1970-01-01T00:16:00Z',healthPermissionsGranted=True)

    def test_normalizes_actual_fields_without_inventing_missing_readings(self):
        value,recorded=normalize_snapshot(self.sample(),now=1002)
        self.assertEqual(recorded,1000)
        self.assertEqual(value['source'],'adb')
        self.assertEqual(value['health']['steps'],2500)
        self.assertNotIn('bpm',value['health'])
        self.assertNotIn('sleepMinutes',value['health'])
        self.assertEqual(value['location']['recordedAt'],'1970-01-01T00:16:35Z')
        self.assertNotIn('healthPermissionsGranted',value['health'])

    def test_rejects_stale_and_future_snapshots(self):
        for now in [999,1100]:
            with self.assertRaises(ValueError):normalize_snapshot(self.sample(),now=now)

    def test_invalid_coordinates_and_nonfinite_health_are_not_exposed(self):
        value,_=normalize_snapshot({**self.sample(),'latitude':91,'bpm':float('nan')},now=1002)
        self.assertIsNone(value['location'])
        self.assertNotIn('bpm',value['health'])

class PhoneUsbTests(unittest.IsolatedAsyncioTestCase):
    async def test_wifi_metadata_failure_does_not_break_usb_telemetry(self):
        async def fake(*args,**kwargs):
            if 'wlan0' in args:raise OSError()
            if 'getprop' in args:return 'SM-S952U1'
            return '{}'
        with mock.patch('phone_telemetry.shutil.which',return_value='/adb'),mock.patch('phone_telemetry.command',side_effect=fake),mock.patch('phone_telemetry.normalize_snapshot',return_value=({'health':{},'source':'adb'},123)):
            phone,data=await read_phone()
        self.assertTrue(phone['connected'])
        self.assertIsNone(phone['ip'])
        self.assertNotIn('serial',phone)
