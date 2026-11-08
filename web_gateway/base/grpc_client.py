"""
SmartCrop AI Client.
Supports both:
  1. HTTPS/HTTP REST API (via AI_SERVICE_URL - primary for Render / Vercel cloud architecture).
  2. Native gRPC Channel (via GRPC_AI_HOST - for local or direct gRPC deployments).
Preserves the exact function interfaces required by Django views.
"""

import os
import logging
import requests
import grpc
from . import plant_pb2
from . import plant_pb2_grpc

logger = logging.getLogger(__name__)


# =========================================================
# 1. HTTP REST CLIENT (RENDER & VERCEL ARCHITECTURE)
# =========================================================

def get_ai_service_url():
    """Returns the normalized AI HTTP Service URL or None."""
    raw_url = os.environ.get('AI_SERVICE_URL', '').strip()
    if not raw_url:
        return None
    # Normalize: strip trailing slashes
    clean_url = raw_url.rstrip('/')
    if not clean_url.startswith('http://') and not clean_url.startswith('https://'):
        clean_url = f"https://{clean_url}"
    return clean_url


def call_predict_disease_http(base_url, image_bytes, timeout=10):
    """Calls the HTTP endpoint /predict/disease."""
    url = f"{base_url}/predict/disease"
    try:
        files = {'image': ('specimen.jpg', image_bytes, 'image/jpeg')}
        response = requests.post(url, files=files, timeout=timeout)

        if response.status_code == 200:
            data = response.json()
            logger.info(f"[AI HTTP] Disease prediction success from {base_url}: {data.get('result')}")
            return True, data, None
        else:
            err_msg = f"AI Service returned HTTP {response.status_code}: {response.text[:200]}"
            logger.error(f"[AI HTTP Error] {err_msg}")
            return False, None, err_msg

    except requests.exceptions.Timeout:
        err_msg = f"AI Service timeout ({timeout}s) connecting to {base_url}. Service may be waking from cold sleep."
        logger.warning(f"[AI HTTP Timeout] {err_msg}")
        return False, None, err_msg

    except requests.exceptions.RequestException as req_err:
        err_msg = f"AI Service connection error: {str(req_err)}"
        logger.error(f"[AI HTTP Error] {err_msg}")
        return False, None, err_msg


def call_predict_water_http(base_url, avg_temp, avg_hum, avg_soil, timeout=5):
    """Calls the HTTP endpoint /predict/water."""
    url = f"{base_url}/predict/water"
    try:
        payload = {
            "avg_temperature": float(avg_temp),
            "avg_humidity": float(avg_hum),
            "avg_soil_moisture": float(avg_soil)
        }
        response = requests.post(url, json=payload, timeout=timeout)

        if response.status_code == 200:
            data = response.json()
            liters = float(data.get("predicted_water_liters", 0.0))
            logger.info(f"[AI HTTP] Water prediction from {base_url}: {liters} L")
            return True, liters, None
        else:
            err_msg = f"AI Service water endpoint returned HTTP {response.status_code}"
            logger.warning(f"[AI HTTP Warning] {err_msg}")
            return False, None, err_msg

    except Exception as e:
        logger.warning(f"[AI HTTP Water Warning] Failed calling {base_url}: {e}")
        return False, None, str(e)


# =========================================================
# 2. NATIVE gRPC CLIENT (FALLBACK / LOCAL DEVELOPMENT)
# =========================================================

def get_grpc_target_and_ssl():
    """Parses GRPC_AI_HOST environment variable."""
    raw_host = os.environ.get('GRPC_AI_HOST', 'localhost:50051').strip()
    use_ssl = False

    if raw_host.startswith('https://'):
        raw_host = raw_host[8:]
        use_ssl = True
    elif raw_host.startswith('http://'):
        raw_host = raw_host[7:]
        use_ssl = False

    clean_host = raw_host.split('/')[0].strip()

    ssl_env = os.environ.get('GRPC_AI_USE_SSL', '').strip().lower()
    if ssl_env in ('true', '1', 'yes'):
        use_ssl = True
    elif ssl_env in ('false', '0', 'no'):
        use_ssl = False
    elif ':443' in clean_host:
        use_ssl = True
    elif not clean_host.startswith('localhost') and not clean_host.startswith('127.0.0.1'):
        if ':' not in clean_host:
            clean_host = f"{clean_host}:443"
            use_ssl = True

    return clean_host, use_ssl


def get_grpc_channel(timeout_sec=5):
    """Creates a secure or insecure gRPC channel."""
    target, use_ssl = get_grpc_target_and_ssl()
    options = [
        ('grpc.max_receive_message_length', 50 * 1024 * 1024),
        ('grpc.max_send_message_length', 50 * 1024 * 1024),
        ('grpc.enable_retries', 1),
    ]

    if use_ssl:
        credentials = grpc.ssl_channel_credentials()
        return grpc.secure_channel(target, credentials, options=options)
    else:
        return grpc.insecure_channel(target, options=options)


def call_predict_disease_grpc(image_bytes, timeout=10):
    """Calls the PredictDisease RPC method."""
    target, use_ssl = get_grpc_target_and_ssl()
    try:
        with get_grpc_channel() as channel:
            stub = plant_pb2_grpc.PlantServiceStub(channel)
            request = plant_pb2.PlantRequest(image=image_bytes)
            response = stub.PredictDisease(request, timeout=timeout)

            confidence_percent = int(response.confidence * 100)
            data = {
                "prediction": response.prediction,
                "result": f"{response.prediction} ({confidence_percent}%)",
                "confidence": response.confidence,
                "confidence_percent": confidence_percent,
                "disease_type": response.disease_type,
                "treatment": response.treatment,
            }
            logger.info(f"[gRPC] Success from {target}: {data['result']}")
            return True, data, None

    except grpc.RpcError as rpc_err:
        code = rpc_err.code()
        details = rpc_err.details()
        err_msg = f"gRPC RpcError [{code}]: {details} (target={target}, ssl={use_ssl})"
        logger.error(f"[gRPC Error] {err_msg}")
        return False, None, err_msg

    except Exception as e:
        err_msg = f"Unexpected gRPC error: {str(e)} (target={target}, ssl={use_ssl})"
        logger.error(f"[gRPC Error] {err_msg}")
        return False, None, err_msg


def call_predict_water_grpc(avg_temp, avg_hum, avg_soil, timeout=5):
    """Calls the PredictWaterNeed RPC method."""
    target, use_ssl = get_grpc_target_and_ssl()
    try:
        with get_grpc_channel() as channel:
            stub = plant_pb2_grpc.PlantServiceStub(channel)
            request = plant_pb2.WaterRequest(
                avg_temperature=avg_temp,
                avg_humidity=avg_hum,
                avg_soil_moisture=avg_soil
            )
            response = stub.PredictWaterNeed(request, timeout=timeout)
            logger.info(f"[gRPC] Water prediction from {target}: {response.predicted_water_liters} L")
            return True, response.predicted_water_liters, None

    except Exception as e:
        logger.warning(f"[gRPC Water Warning] Failed calling {target}: {e}")
        return False, None, str(e)


# =========================================================
# 3. PUBLIC INTERFACES (PRESERVED FOR DJANGO VIEWS)
# =========================================================

def call_predict_disease(image_bytes, timeout=10):
    """
    Main disease prediction function called by Django views.
    Routes to HTTP REST API if AI_SERVICE_URL is set, otherwise falls back to gRPC.
    """
    ai_url = get_ai_service_url()
    if ai_url:
        return call_predict_disease_http(ai_url, image_bytes, timeout=timeout)
    else:
        return call_predict_disease_grpc(image_bytes, timeout=timeout)


def call_predict_water(avg_temp, avg_hum, avg_soil, timeout=5):
    """
    Main water prediction function called by Django views.
    Routes to HTTP REST API if AI_SERVICE_URL is set, otherwise falls back to gRPC.
    """
    ai_url = get_ai_service_url()
    if ai_url:
        return call_predict_water_http(ai_url, avg_temp, avg_hum, avg_soil, timeout=timeout)
    else:
        return call_predict_water_grpc(avg_temp, avg_hum, avg_soil, timeout=timeout)
