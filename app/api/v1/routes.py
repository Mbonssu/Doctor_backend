"""
DoctoPing API — tous les routers v1
Correspond exactement aux endpoints définis dans api_config.dart du frontend Flutter.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.security import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, decode_token, get_current_user,
    require_doctor, require_patient,
)
from ...models.models import User
from ...repositories.repositories import (
    UserRepository, DoctorRepository, AppointmentRepository,
    ReviewRepository, RefreshTokenRepository, ScheduleRepository,
    NotificationRepository,
)
from ...schemas.schemas import (
    LoginRequest, RegisterRequest, AuthResponse, RefreshRequest,
    ForgotPasswordRequest, ResetPasswordRequest, VerifyEmailRequest,
    UserOut, UserUpdate, ChangePasswordRequest,
    DoctorOut, DoctorListResponse, DoctorUpdate,
    AppointmentOut, AppointmentListResponse, AppointmentCreate,
    AppointmentUpdate, CancelAppointmentRequest,
    AvailabilityCheckRequest, AvailabilityCheckResponse,
    ReviewOut, ReviewListResponse, ReviewCreate, ReviewUpdate,
    WeekScheduleOut, ScheduleUpdate,
    NotificationOut, UnreadCountOut,
)
from ...core.config import settings


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH  /api/v1/auth
# ═══════════════════════════════════════════════════════════════════════════════

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    access_token  = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    rt_repo = RefreshTokenRepository(db)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    await rt_repo.create(user.id, refresh_token, expires_at)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )


@auth_router.post("/register", response_model=AuthResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    if await repo.get_by_email(body.email):
        raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")

    user = await repo.create(
        email=body.email,
        hashed_password=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        role=body.role,
        phone=body.phone,
    )

    # Si rôle médecin, créer un profil doctor vide
    if body.role == "doctor":
        dr_repo = DoctorRepository(db)
        await dr_repo.create(
            user_id=user.id,
            specialty="Non renseignée",
            license_number=f"TEMP-{user.id}",
        )

    access_token  = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    rt_repo = RefreshTokenRepository(db)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    await rt_repo.create(user.id, refresh_token, expires_at)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )


@auth_router.post("/refresh")
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token de type invalide")

    rt_repo = RefreshTokenRepository(db)
    stored = await rt_repo.get(body.refresh_token)
    if not stored or stored.is_revoked or stored.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token invalide ou expiré")

    user_id = int(payload["sub"])
    new_access  = create_access_token({"sub": str(user_id)})
    new_refresh = create_refresh_token({"sub": str(user_id)})

    await rt_repo.revoke(body.refresh_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    await rt_repo.create(user_id, new_refresh, expires_at)

    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}


@auth_router.post("/logout", status_code=204)
async def logout(body: dict, db: AsyncSession = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    rt_repo = RefreshTokenRepository(db)
    refresh = body.get("refresh_token")
    if refresh:
        await rt_repo.revoke(refresh)


@auth_router.post("/forgot-password", status_code=204)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    # En production : générer un token + envoyer un email
    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)
    if user:
        pass  # TODO: send email with reset link
    # On ne révèle pas si l'email existe
    return


@auth_router.post("/reset-password", status_code=204)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    # En production : vérifier le token de reset
    # TODO: implémenter la vérification du token de reset
    return


@auth_router.post("/verify-email", status_code=204)
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    # TODO: vérifier le code envoyé par email
    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)
    if user:
        await repo.verify(user.id)


@auth_router.post("/send-verification-code", status_code=204)
async def send_verification_code(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    # TODO: générer et envoyer le code par email
    return


# ═══════════════════════════════════════════════════════════════════════════════
# USERS  /api/v1/users
# ═══════════════════════════════════════════════════════════════════════════════

users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@users_router.put("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = UserRepository(db)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return UserOut.model_validate(current_user)
    user = await repo.update(current_user.id, **updates)
    return UserOut.model_validate(user)


@users_router.post("/me/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    repo = UserRepository(db)
    await repo.update(current_user.id, hashed_password=hash_password(body.new_password))


@users_router.get("/me/stats")
async def get_my_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    apt_repo = AppointmentRepository(db)
    stats = await apt_repo.get_doctor_stats(current_user.id) if current_user.role == "doctor" else {}
    return stats


@users_router.get("/me/health-summary")
async def get_health_summary(current_user: User = Depends(get_current_user)):
    # TODO: implémenter le résumé de santé
    return {"message": "Health summary à implémenter"}


# ═══════════════════════════════════════════════════════════════════════════════
# DOCTORS  /api/v1/doctors
# ═══════════════════════════════════════════════════════════════════════════════

doctors_router = APIRouter(prefix="/doctors", tags=["Doctors"])


@doctors_router.get("", response_model=DoctorListResponse)
async def search_doctors(
    query: Optional[str] = Query(None),
    specialty: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    is_available: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    repo = DoctorRepository(db)
    doctors, total = await repo.search(query=query, specialty=specialty, city=city,
                                        is_available=is_available, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size
    return DoctorListResponse(
        doctors=[DoctorOut.model_validate(d) for d in doctors],
        total=total, page=page, page_size=page_size, total_pages=total_pages,
    )


@doctors_router.get("/top-rated", response_model=list[DoctorOut])
async def get_top_rated(limit: int = Query(10, ge=1, le=50), db: AsyncSession = Depends(get_db)):
    repo = DoctorRepository(db)
    doctors = await repo.get_top_rated(limit=limit)
    return [DoctorOut.model_validate(d) for d in doctors]


@doctors_router.get("/recommended", response_model=list[DoctorOut])
async def get_recommended(
    limit: int = Query(10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Simplification : retourner les mieux notés
    repo = DoctorRepository(db)
    doctors = await repo.get_top_rated(limit=limit)
    return [DoctorOut.model_validate(d) for d in doctors]


@doctors_router.get("/specialty/{specialty}", response_model=DoctorListResponse)
async def get_by_specialty(
    specialty: str,
    page: int = Query(1), page_size: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    repo = DoctorRepository(db)
    doctors, total = await repo.search(specialty=specialty, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size
    return DoctorListResponse(
        doctors=[DoctorOut.model_validate(d) for d in doctors],
        total=total, page=page, page_size=page_size, total_pages=total_pages,
    )


@doctors_router.get("/{doctor_id}", response_model=DoctorOut)
async def get_doctor(doctor_id: int, db: AsyncSession = Depends(get_db)):
    repo = DoctorRepository(db)
    doctor = await repo.get_by_id(doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Médecin introuvable")
    return DoctorOut.model_validate(doctor)


@doctors_router.put("/me", response_model=DoctorOut)
async def update_doctor_profile(
    body: DoctorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor),
):
    dr_repo = DoctorRepository(db)
    doctor = await dr_repo.get_by_user_id(current_user.id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Profil médecin introuvable")
    updates = body.model_dump(exclude_none=True)
    doctor = await dr_repo.update(doctor.id, **updates)
    return DoctorOut.model_validate(doctor)


# ─── Schedule du médecin ──────────────────────────────────────────────────────

@doctors_router.get("/me/schedule", response_model=WeekScheduleOut)
async def get_my_schedule(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor),
):
    dr_repo = DoctorRepository(db)
    doctor = await dr_repo.get_by_user_id(current_user.id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Profil médecin introuvable")
    sched_repo = ScheduleRepository(db)
    schedules = await sched_repo.get_week_schedule(doctor.id)
    slots = await sched_repo.get_slots(doctor.id)
    return WeekScheduleOut(schedules=schedules, slots=slots)


@doctors_router.put("/me/schedule", response_model=WeekScheduleOut)
async def update_my_schedule(
    body: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor),
):
    dr_repo = DoctorRepository(db)
    doctor = await dr_repo.get_by_user_id(current_user.id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Profil médecin introuvable")

    sched_repo = ScheduleRepository(db)
    await sched_repo.upsert_schedule(
        doctor_id=doctor.id,
        day_of_week=body.day_of_week,
        is_working_day=body.is_working_day,
        consult_duration_min=body.consult_duration_min,
        break_duration_min=body.break_duration_min,
        max_patients=body.max_patients,
    )
    await sched_repo.sync_slots(doctor.id, body.day_of_week, body.slots)

    schedules = await sched_repo.get_week_schedule(doctor.id)
    slots = await sched_repo.get_slots(doctor.id)
    return WeekScheduleOut(schedules=schedules, slots=slots)


# ─── Stats du médecin ─────────────────────────────────────────────────────────

@doctors_router.get("/me/stats")
async def get_doctor_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor),
):
    dr_repo = DoctorRepository(db)
    doctor = await dr_repo.get_by_user_id(current_user.id)
    if not doctor:
        raise HTTPException(404, "Profil médecin introuvable")
    apt_repo = AppointmentRepository(db)
    stats = await apt_repo.get_doctor_stats(doctor.id)
    return {
        **stats,
        "total_patients": doctor.total_patients,
        "rating": doctor.rating,
        "total_reviews": doctor.total_reviews,
    }


# ─── RDV du médecin ───────────────────────────────────────────────────────────

@doctors_router.get("/me/appointments", response_model=AppointmentListResponse)
async def get_doctor_appointments(
    status: Optional[str] = Query(None),
    page: int = Query(1), page_size: int = Query(20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor),
):
    dr_repo = DoctorRepository(db)
    doctor = await dr_repo.get_by_user_id(current_user.id)
    if not doctor:
        raise HTTPException(404, "Profil médecin introuvable")
    apt_repo = AppointmentRepository(db)
    appointments, total = await apt_repo.get_doctor_appointments(doctor.id, status=status,
                                                                   page=page, page_size=page_size)
    return AppointmentListResponse(
        appointments=[AppointmentOut.model_validate(a) for a in appointments],
        total=total, page=page, page_size=page_size,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# APPOINTMENTS  /api/v1/appointments
# ═══════════════════════════════════════════════════════════════════════════════

appointments_router = APIRouter(prefix="/appointments", tags=["Appointments"])


@appointments_router.post("", response_model=AppointmentOut, status_code=201)
async def create_appointment(
    body: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dr_repo = DoctorRepository(db)
    doctor = await dr_repo.get_by_id(body.doctor_id)
    if not doctor:
        raise HTTPException(404, "Médecin introuvable")

    apt_repo = AppointmentRepository(db)
    available = await apt_repo.check_availability(body.doctor_id, body.appointment_date, body.duration_minutes)
    if not available:
        raise HTTPException(409, "Ce créneau n'est plus disponible")

    apt = await apt_repo.create(
        patient_id=body.patient_id,
        doctor_id=body.doctor_id,
        appointment_date=body.appointment_date,
        duration_minutes=body.duration_minutes,
        appointment_type=body.appointment_type,
        consultation_fee=doctor.consultation_fee,
        reason=body.reason,
        notes=body.notes,
    )

    # Notifier le médecin
    notif_repo = NotificationRepository(db)
    user_repo = UserRepository(db)
    patient = await user_repo.get_by_id(body.patient_id)
    await notif_repo.create(
        user_id=doctor.user_id,
        title="Nouveau rendez-vous",
        message=f"{patient.first_name} {patient.last_name} a pris un RDV le {apt.appointment_date.strftime('%d/%m à %H:%M')}",
        notif_type="appointment",
    )

    return AppointmentOut.model_validate(apt)


@appointments_router.get("/my-appointments", response_model=AppointmentListResponse)
async def get_my_appointments(
    status: Optional[str] = Query(None),
    page: int = Query(1), page_size: int = Query(20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = AppointmentRepository(db)
    appointments, total = await repo.get_my_appointments(current_user.id, status=status,
                                                          page=page, page_size=page_size)
    return AppointmentListResponse(
        appointments=[AppointmentOut.model_validate(a) for a in appointments],
        total=total, page=page, page_size=page_size,
    )


@appointments_router.get("/upcoming", response_model=list[AppointmentOut])
async def get_upcoming(
    limit: int = Query(10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = AppointmentRepository(db)
    appointments = await repo.get_upcoming(current_user.id, limit=limit)
    return [AppointmentOut.model_validate(a) for a in appointments]


@appointments_router.get("/next", response_model=Optional[AppointmentOut])
async def get_next(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = AppointmentRepository(db)
    apt = await repo.get_next(current_user.id)
    return AppointmentOut.model_validate(apt) if apt else None


@appointments_router.post("/check-availability", response_model=AvailabilityCheckResponse)
async def check_availability(body: AvailabilityCheckRequest, db: AsyncSession = Depends(get_db)):
    repo = AppointmentRepository(db)
    available = await repo.check_availability(body.doctor_id, body.appointment_date, body.duration_minutes)
    return AvailabilityCheckResponse(
        is_available=available,
        message="Créneau disponible" if available else "Créneau déjà pris",
    )


@appointments_router.get("/{appointment_id}", response_model=AppointmentOut)
async def get_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = AppointmentRepository(db)
    apt = await repo.get_by_id(appointment_id)
    if not apt:
        raise HTTPException(404, "Rendez-vous introuvable")
    if apt.patient_id != current_user.id and current_user.role not in ("doctor", "admin"):
        raise HTTPException(403, "Accès refusé")
    return AppointmentOut.model_validate(apt)


@appointments_router.put("/{appointment_id}", response_model=AppointmentOut)
async def update_appointment(
    appointment_id: int,
    body: AppointmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = AppointmentRepository(db)
    apt = await repo.get_by_id(appointment_id)
    if not apt:
        raise HTTPException(404, "Rendez-vous introuvable")

    updates = body.model_dump(exclude_none=True)
    apt = await repo.update(appointment_id, **updates)
    return AppointmentOut.model_validate(apt)


@appointments_router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
async def cancel_appointment(
    appointment_id: int,
    body: CancelAppointmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = AppointmentRepository(db)
    apt = await repo.get_by_id(appointment_id)
    if not apt:
        raise HTTPException(404, "Rendez-vous introuvable")
    if apt.status in ("completed", "cancelled"):
        raise HTTPException(400, f"Impossible d'annuler un RDV {apt.status}")

    cancelled_by = "patient" if current_user.role == "patient" else "doctor"
    apt = await repo.cancel(appointment_id, cancelled_by=cancelled_by, reason=body.cancellation_reason)
    return AppointmentOut.model_validate(apt)


# ═══════════════════════════════════════════════════════════════════════════════
# REVIEWS  /api/v1/reviews
# ═══════════════════════════════════════════════════════════════════════════════

reviews_router = APIRouter(prefix="/reviews", tags=["Reviews"])


@reviews_router.get("/doctor/{doctor_id}", response_model=ReviewListResponse)
async def get_doctor_reviews(
    doctor_id: int,
    page: int = Query(1), page_size: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    repo = ReviewRepository(db)
    reviews, total, avg = await repo.get_doctor_reviews(doctor_id, page=page, page_size=page_size)
    return ReviewListResponse(
        reviews=reviews, total=total, page=page, page_size=page_size, average_rating=avg,
    )


@reviews_router.post("", response_model=ReviewOut, status_code=201)
async def create_review(
    body: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = ReviewRepository(db)
    review = await repo.create(body.doctor_id, body.patient_id, body.rating, body.comment)
    # Recalculer la note du médecin
    dr_repo = DoctorRepository(db)
    await dr_repo.update_rating(body.doctor_id)
    return ReviewOut.model_validate(review)


@reviews_router.get("/{review_id}", response_model=ReviewOut)
async def get_review(review_id: int, db: AsyncSession = Depends(get_db)):
    repo = ReviewRepository(db)
    review = await repo.get_by_id(review_id)
    if not review:
        raise HTTPException(404, "Avis introuvable")
    return ReviewOut.model_validate(review)


@reviews_router.put("/{review_id}", response_model=ReviewOut)
async def update_review(
    review_id: int, body: ReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = ReviewRepository(db)
    review = await repo.get_by_id(review_id)
    if not review:
        raise HTTPException(404, "Avis introuvable")
    if review.patient_id != current_user.id:
        raise HTTPException(403, "Vous ne pouvez modifier que vos propres avis")
    updates = body.model_dump(exclude_none=True)
    review = await repo.update(review_id, **updates)
    dr_repo = DoctorRepository(db)
    await dr_repo.update_rating(review.doctor_id)
    return ReviewOut.model_validate(review)


@reviews_router.delete("/{review_id}", status_code=204)
async def delete_review(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = ReviewRepository(db)
    review = await repo.get_by_id(review_id)
    if not review:
        raise HTTPException(404, "Avis introuvable")
    if review.patient_id != current_user.id and current_user.role != "admin":
        raise HTTPException(403, "Accès refusé")
    doctor_id = review.doctor_id
    await repo.delete(review_id)
    dr_repo = DoctorRepository(db)
    await dr_repo.update_rating(doctor_id)


# ═══════════════════════════════════════════════════════════════════════════════
# FAVORITES  /api/v1/favorite-doctors
# ═══════════════════════════════════════════════════════════════════════════════

favorites_router = APIRouter(prefix="/favorite-doctors", tags=["Favorites"])


@favorites_router.get("", response_model=list[DoctorOut])
async def get_favorites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # TODO: implémenter les favoris
    return []


@favorites_router.post("/{doctor_id}", status_code=201)
async def add_favorite(
    doctor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"message": "Ajouté aux favoris"}


@favorites_router.delete("/{doctor_id}", status_code=204)
async def remove_favorite(
    doctor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS  /api/v1/notifications
# ═══════════════════════════════════════════════════════════════════════════════

notifications_router = APIRouter(prefix="/notifications", tags=["Notifications"])


@notifications_router.get("/unread/count", response_model=UnreadCountOut)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationRepository(db)
    count = await repo.get_unread_count(current_user.id)
    return UnreadCountOut(count=count)
