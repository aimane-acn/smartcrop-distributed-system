from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from .models import Profile, History, SensorData
from .grpc_client import get_grpc_target_and_ssl
import os


class GRPCClientConfigTests(TestCase):
    def test_grpc_target_cleaning(self):
        # Test default
        if 'GRPC_AI_HOST' in os.environ:
            del os.environ['GRPC_AI_HOST']
        target, ssl = get_grpc_target_and_ssl()
        self.assertEqual(target, 'localhost:50051')
        self.assertFalse(ssl)

        # Test URL with https://
        os.environ['GRPC_AI_HOST'] = 'https://smartcrop-ai.onrender.com'
        target, ssl = get_grpc_target_and_ssl()
        self.assertEqual(target, 'smartcrop-ai.onrender.com:443')
        self.assertTrue(ssl)

        # Test URL with http://
        os.environ['GRPC_AI_HOST'] = 'http://127.0.0.1:50051'
        target, ssl = get_grpc_target_and_ssl()
        self.assertEqual(target, '127.0.0.1:50051')
        self.assertFalse(ssl)

        # Test remote domain with custom port 443
        os.environ['GRPC_AI_HOST'] = 'my-ai.railway.app:443'
        target, ssl = get_grpc_target_and_ssl()
        self.assertEqual(target, 'my-ai.railway.app:443')
        self.assertTrue(ssl)

        # Cleanup
        if 'GRPC_AI_HOST' in os.environ:
            del os.environ['GRPC_AI_HOST']


class StorageAndModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testfarmer', password='password123')
        self.client = Client()

    def test_history_creation_with_file(self):
        # Create dummy image file
        image_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4'
        uploaded_image = SimpleUploadedFile("sample_leaf.png", image_content, content_type="image/png")

        history = History.objects.create(
            user=self.user,
            image=uploaded_image,
            result="Tomato___healthy (98%)",
            disease_type="Healthy Crop",
            treatment="Regular watering and monitoring."
        )

        self.assertEqual(history.user, self.user)
        self.assertTrue(bool(history.image))
        self.assertTrue(history.image.url.endswith('sample_leaf.png') or 'sample_leaf' in history.image.url)

    def test_optimization_formula_fallback(self):
        SensorData.objects.create(
            device_id="node_01",
            temperature=28.0,
            humidity=60.0,
            soil_moisture=45.0
        )
        self.client.login(username='testfarmer', password='password123')
        response = self.client.get('/optimization/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('predicted_water', response.context)
        # Expected: 5.0 + (28 * 0.2) - (60 * 0.05) - (45 * 0.1) = 5.0 + 5.6 - 3.0 - 4.5 = 3.1
        self.assertAlmostEqual(response.context['predicted_water'], 3.1, places=1)
