"""
gRPC Client Helper for SmartCrop AI Microservice.
Supports dynamic host discovery, auto-detection of SSL/TLS vs plaintext channels,
URL sanitization, and structured error logging.
"""

import os
import logging
import grpc
from . import plant_pb2
from . import plant_pb2_grpc

logger = logging.getLogger(__name__)


def get_grpc_target_and_ssl():
    """
    Parses the GRPC_AI_HOST environment variable.
    Returns a tuple of (clean_target_string, use_ssl_bool).
    """
    raw_host = os.environ.get('GRPC_AI_HOST', 'localhost:50051').strip()
    use_ssl = False

    # 1. Sanitize protocol schemes if user accidentally included them
    if raw_host.startswith('https://'):
        raw_host = raw_host[8:]
        use_ssl = True
    elif raw_host.startswith('http://'):
        raw_host = raw_host[7:]
        use_ssl = False

    # Remove any trailing slashes or URL paths
    clean_host = raw_host.split('/')[0].strip()

    # 2. Check explicit SSL override
    ssl_env = os.environ.get('GRPC_AI_USE_SSL', '').strip().lower()
    if ssl_env in ('true', '1', 'yes'):
        use_ssl = True
    elif ssl_env in ('false', '0', 'no'):
        use_ssl = False
    elif ':443' in clean_host:
        use_ssl = True
    elif not clean_host.startswith('localhost') and not clean_host.startswith('127.0.0.1'):
        # If it's a remote domain without a custom port (e.g., smartcrop.onrender.com), default to SSL port 443
        if ':' not in clean_host:
            clean_host = f"{clean_host}:443"
            use_ssl = True

    return clean_host, use_ssl


def get_grpc_channel(timeout_sec=5):
    """
    Creates an appropriate secure or insecure gRPC channel.
    """
    target, use_ssl = get_grpc_target_and_ssl()
    
    # Configure gRPC options for production reliability
    options = [
        ('grpc.max_receive_message_length', 50 * 1024 * 1024),
        ('grpc.max_send_message_length', 50 * 1024 * 1024),
        ('grpc.enable_retries', 1),
    ]

    if use_ssl:
        logger.info(f"[gRPC] Connecting via SECURE channel (TLS) to: {target}")
        credentials = grpc.ssl_channel_credentials()
        return grpc.secure_channel(target, credentials, options=options)
    else:
        logger.info(f"[gRPC] Connecting via INSECURE channel to: {target}")
        return grpc.insecure_channel(target, options=options)


def call_predict_disease(image_bytes, timeout=10):
    """
    Calls the PredictDisease RPC method.
    Returns: (is_success, data_dict, error_message)
    """
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


def call_predict_water(avg_temp, avg_hum, avg_soil, timeout=5):
    """
    Calls the PredictWaterNeed RPC method.
    Returns: (is_success, predicted_water_liters, error_message)
    """
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
