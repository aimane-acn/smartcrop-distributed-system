from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator
from django.conf import settings
import os
import base64
import grpc
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from django.utils import timezone  # ✅ ajouté

from .forms import CustomUserCreationForm, UserUpdateForm, ProfileUpdateForm
from .models import History, SensorData

from . import plant_pb2
from . import plant_pb2_grpc


# --- BASIC VIEWS ---

def home(request):
    return render(request, 'base/home.html')


def signup(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'base/signup.html', {'form': form})


def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("dashbord")
    else:
        form = AuthenticationForm()
    return render(request, 'base/login.html', {"form": form})


def logout_view(request):
    if request.method == "POST":
        logout(request)
        return redirect("home")


# --- DASHBOARD (LATEST DATA) ---

@login_required
def dashbord(request):
    profile = request.user.profile
    latest_sensor = SensorData.objects.order_by('-timestamp').first()
    
    # If no data exists, provide fallback defaults for UI
    if not latest_sensor:
        class MockSensor:
            temperature = 0.0
            humidity = 0.0
            soil_moisture = 0.0
        latest_sensor = MockSensor()

    return render(request, 'base/dashbord.html', {
        "profile": profile,
        "latest_sensor": latest_sensor,
    })


# --- ANALYZE IMAGE (gRPC) ---

@login_required
def analyze_image(request):
    image_url = None
    result = None
    disease_type = None
    treatment = None

    if request.method == "POST" and request.FILES.get("image"):
        image = request.FILES["image"]

        # 1. Safe storage handling for Serverless / Vercel
        filename = image.name
        try:
            fs = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)
            filename = fs.save(image.name, image)
            image_url = fs.url(filename)
        except Exception as e:
            print("File save warning:", e)
            filename = image.name

        image.seek(0)
        image_bytes = image.read()

        # 2. Base64 Preview: Guarantees the uploaded image renders in the browser on Vercel
        try:
            encoded = base64.b64encode(image_bytes).decode('utf-8')
            c_type = getattr(image, 'content_type', None) or 'image/jpeg'
            image_url = f"data:{c_type};base64,{encoded}"
        except Exception:
            pass

        # 3. Call gRPC service (with timeout and fallback message)
        grpc_host = os.environ.get('GRPC_AI_HOST', 'localhost:50051')
        try:
            with grpc.insecure_channel(grpc_host) as channel:
                stub = plant_pb2_grpc.PlantServiceStub(channel)
                grpc_request = plant_pb2.PlantRequest(image=image_bytes)
                grpc_response = stub.PredictDisease(grpc_request, timeout=3)

                confidence_percent = int(grpc_response.confidence * 100)
                result = f"{grpc_response.prediction} ({confidence_percent}%)"
                disease_type = grpc_response.disease_type
                treatment = grpc_response.treatment

        except Exception as e:
            result = "AI Model Unreachable (gRPC offline)"
            disease_type = "Distributed AI Service"
            treatment = "The PyTorch AI inference runs in a separate gRPC microservice (ai_service/server.py). Connect your AI server URL or run it locally to see real-time disease detections."
            print("gRPC error:", e)

        try:
            History.objects.create(
                user=request.user,
                image=filename,
                result=result,
                disease_type=disease_type,
                treatment=treatment
            )
        except Exception as e:
            print("History save warning:", e)

    profile = request.user.profile
    return render(request, 'base/analyze.html', {
        "result": result,
        "disease_type": disease_type,
        "treatment": treatment,
        "image_url": image_url,
        "profile": profile
    })


# --- HISTORY ---

@login_required
def history(request):
    items = History.objects.filter(user=request.user).order_by('-id')
    profile = request.user.profile

    paginator = Paginator(items, 5)
    page = request.GET.get('page')
    items_page = paginator.get_page(page)

    return render(request, "base/history.html", {
        "items": items_page,
        "profile": profile,
    })


@login_required
def delete_history(request, pk):
    item = get_object_or_404(History, id=pk, user=request.user)
    if request.method == "POST":
        item.delete()
    return redirect("history")

from django.db import connection, transaction

@login_required
def clear_all_history(request):
    if request.method == "POST":
        # Delete ALL history for ALL users so the ID can truly reset to 1
        History.objects.all().delete()
        
        # Reset the ID counter (auto-increment) back to 1 for a clean demo
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name='base_history';")
        except Exception as e:
            print("Could not reset sequence:", e)
            
    return redirect("history")


# --- PROFILE ---

@login_required
def edit_profile(request):
    user = request.user
    profile = user.profile

    if request.method == "POST":
        user_form = UserUpdateForm(request.POST, instance=user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            return redirect("dashbord")
    else:
        user_form = UserUpdateForm(instance=user)
        profile_form = ProfileUpdateForm(instance=profile)

    return render(request, "base/edit_profile.html", {
        "user_form": user_form,
        "profile_form": profile_form
    })


# =========================================================
# ✅ FIXED IoT ENDPOINT (ANTI-DUPLICATES)
# =========================================================

@csrf_exempt
def iot_data_ingest(request):
    """Endpoint for ESP32/Wokwi to send sensor data (filtered)."""

    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            device_id = data.get('device_id', 'unknown')
            sensors = data.get('sensors', {})

            new_temp = sensors.get('air_temperature_c', 0.0)
            new_hum = sensors.get('air_humidity_percent', 0.0)
            new_soil = sensors.get('soil_moisture_percent', 0.0)

            # 🔥 Get last record for this device
            last = SensorData.objects.filter(
                device_id=device_id
            ).order_by('-timestamp').first()

            # 🚫 Ignore if nothing changed
            if last:
                if (
                    abs(last.temperature - new_temp) < 0.1 and
                    abs(last.humidity - new_hum) < 0.1 and
                    abs(last.soil_moisture - new_soil) < 0.1
                ):
                    return JsonResponse({
                        "status": "ignored",
                        "message": "No significant change"
                    })

            # 💾 Save only if changed
            SensorData.objects.create(
                device_id=device_id,
                temperature=new_temp,
                humidity=new_hum,
                soil_moisture=new_soil
            )

            return JsonResponse({"status": "saved"})

        except Exception as e:
            return JsonResponse(
                {"status": "error", "message": str(e)},
                status=400
            )

    return JsonResponse(
        {"status": "error", "message": "Only POST allowed"},
        status=405
    )


# --- OPTIMIZATION DASHBOARD ---

@login_required
def optimization_dashboard(request):
    sensor_history = SensorData.objects.all().order_by('-timestamp')[:10]

    if sensor_history:
        avg_temp = sum(s.temperature for s in sensor_history) / len(sensor_history)
        avg_hum = sum(s.humidity for s in sensor_history) / len(sensor_history)
        avg_soil = sum(s.soil_moisture for s in sensor_history) / len(sensor_history)
    else:
        avg_temp, avg_hum, avg_soil = 25.0, 50.0, 40.0

    # Linear Regression Formula for Water Need (7-day forecast in Liters):
    # base_water = 5.0L + (Temp * 0.2) - (Hum * 0.05) - (Moisture * 0.1)
    base_water = 5.0
    temp_factor = avg_temp * 0.2
    humidity_factor = avg_hum * 0.05
    moisture_factor = avg_soil * 0.1
    calculated_water = round(max(0.5, base_water + temp_factor - humidity_factor - moisture_factor), 2)
    predicted_water = calculated_water

    # If gRPC server is available, fetch live prediction
    try:
        grpc_host = os.environ.get('GRPC_AI_HOST', 'localhost:50051')
        with grpc.insecure_channel(grpc_host) as channel:
            stub = plant_pb2_grpc.PlantServiceStub(channel)
            grpc_req = plant_pb2.WaterRequest(
                avg_temperature=avg_temp,
                avg_humidity=avg_hum,
                avg_soil_moisture=avg_soil
            )
            grpc_res = stub.PredictWaterNeed(grpc_req, timeout=2)
            if grpc_res.predicted_water_liters > 0:
                predicted_water = grpc_res.predicted_water_liters
    except Exception as e:
        # Fallback to local linear regression formula
        predicted_water = calculated_water

    return render(request, 'base/optimization.html', {
        'sensor_history': sensor_history,
        'predicted_water': predicted_water,
        'avg_temp': round(avg_temp, 1),
        'avg_hum': round(avg_hum, 1),
        'avg_soil': round(avg_soil, 1),
        'profile': request.user.profile
    })


# --- RESET DATA ---

@login_required
def reset_iot_data(request):
    if request.method == "POST":
        SensorData.objects.all().delete()
    return redirect('optimization')