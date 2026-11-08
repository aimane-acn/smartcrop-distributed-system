"""
SmartCrop AI Microservice - Render-compatible HTTP REST & internal gRPC API.
Exposes plant disease inference (PyTorch ResNet-18) and water prediction
over HTTPS/HTTP, with internal gRPC server support.
"""

import os
import sys
import io
import time
import logging
import threading

# Configure safe UTF-8 output
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("SmartCrop-AI")

from flask import Flask, request, jsonify

# Import the existing model, transforms, service, and protobufs
from server import (
    PlantService,
    DEVICE,
    CLASS_NAMES,
    MODEL_PATH,
    model,
    transform,
    plant_pb2,
    plant_pb2_grpc
)
from disease_info import DISEASE_INFO

app = Flask(__name__)

# Single instance of the existing PlantService
plant_service = PlantService()

# --- OPTIONAL INTERNAL gRPC DAEMON ---
GRPC_INTERNAL_PORT = int(os.environ.get("GRPC_INTERNAL_PORT", 50051))

def start_internal_grpc():
    try:
        import grpc
        from concurrent import futures
        grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=5),
            options=[
                ('grpc.max_receive_message_length', 50 * 1024 * 1024),
                ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ]
        )
        plant_pb2_grpc.add_PlantServiceServicer_to_server(plant_service, grpc_server)
        grpc_server.add_insecure_port(f"127.0.0.1:{GRPC_INTERNAL_PORT}")
        grpc_server.start()
        logger.info(f"Internal gRPC server running on 127.0.0.1:{GRPC_INTERNAL_PORT}")
        grpc_server.wait_for_termination()
    except Exception as e:
        logger.warning(f"Internal gRPC daemon notice: {e}")

# Start internal gRPC in background thread
grpc_thread = threading.Thread(target=start_internal_grpc, daemon=True)
grpc_thread.start()


# --- HTTP REST ROUTES ---

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Render and uptime monitors."""
    return jsonify({
        "status": "healthy",
        "service": "SmartCrop AI Microservice",
        "architecture": "HTTPS REST API + PyTorch ResNet-18",
        "device": str(DEVICE),
        "disease_classes": len(CLASS_NAMES),
        "model_loaded": model is not None,
        "internal_grpc_port": GRPC_INTERNAL_PORT
    }), 200


@app.route("/predict/disease", methods=["POST"])
def predict_disease():
    """
    Plant disease prediction endpoint.
    Accepts:
      - Multipart form-data with file field 'image'
      - Raw request body (binary image data)
      - JSON with 'image_base64'
    """
    image_bytes = None

    if "image" in request.files:
        image_bytes = request.files["image"].read()
    elif request.data and len(request.data) > 0 and not request.is_json:
        image_bytes = request.data
    elif request.is_json:
        body = request.get_json(silent=True) or {}
        if "image_base64" in body:
            import base64
            try:
                image_bytes = base64.b64decode(body["image_base64"])
            except Exception as e:
                return jsonify({"error": f"Invalid base64 encoding: {e}"}), 400

    if not image_bytes:
        return jsonify({
            "error": "No image data received. Provide a file in 'image' field, raw binary bytes, or JSON 'image_base64'."
        }), 400

    try:
        # Build protobuf request and execute prediction
        grpc_req = plant_pb2.PlantRequest(image=image_bytes)
        grpc_res = plant_service.PredictDisease(grpc_req, None)

        confidence_percent = int(grpc_res.confidence * 100)
        return jsonify({
            "prediction": grpc_res.prediction,
            "confidence": float(grpc_res.confidence),
            "confidence_percent": confidence_percent,
            "result": f"{grpc_res.prediction} ({confidence_percent}%)",
            "disease_type": grpc_res.disease_type,
            "treatment": grpc_res.treatment
        }), 200

    except Exception as e:
        logger.error(f"Inference error: {e}", exc_info=True)
        return jsonify({"error": f"Inference failed: {str(e)}"}), 500


@app.route("/predict/water", methods=["POST"])
def predict_water():
    """
    Water prediction endpoint based on IoT metrics.
    Accepts JSON:
      { "avg_temperature": float, "avg_humidity": float, "avg_soil_moisture": float }
    """
    body = request.get_json(silent=True) or {}
    try:
        temp = float(body.get("avg_temperature", 25.0))
        hum = float(body.get("avg_humidity", 50.0))
        soil = float(body.get("avg_soil_moisture", 40.0))

        grpc_req = plant_pb2.WaterRequest(
            avg_temperature=temp,
            avg_humidity=hum,
            avg_soil_moisture=soil
        )
        grpc_res = plant_service.PredictWaterNeed(grpc_req, None)

        return jsonify({
            "predicted_water_liters": float(grpc_res.predicted_water_liters)
        }), 200

    except Exception as e:
        logger.error(f"Water prediction error: {e}", exc_info=True)
        return jsonify({"error": f"Water prediction failed: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 50051))
    logger.info(f"🚀 Starting SmartCrop AI Microservice on 0.0.0.0:{port}...")
    app.run(host="0.0.0.0", port=port)
