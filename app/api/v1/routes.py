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
    VerifyResetCodeRequest, ResetPasswordWithCodeRequest,
    UserOut, UserUpdate, ChangePasswordRequest,
    DoctorOut, DoctorListResponse, DoctorUpdate,
    AppointmentOut, AppointmentListResponse, AppointmentCreate,
    AppointmentUpdate, CancelAppointmentRequest,
    AvailabilityCheckRequest, AvailabilityCheckResponse,
    ReviewOut, ReviewListResponse, ReviewCreate, ReviewUpdate,
    WeekScheduleOut, ScheduleUpdate,
    NotificationOut, NotificationListResponse, UnreadCountOut,
    FamilyMemberOut, FamilyMemberCreate,
    SupportContactRequest,
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
    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)
    if user:
        # TODO: générer OTP 6 chiffres, stocker en cache Redis, envoyer par email
        # Pour le dev: log l'OTP en console
        import random
        otp = str(random.randint(100000, 999999))
        print(f"[DEV] OTP reset password pour {body.email}: {otp}")
    return


@auth_router.post("/reset-password/verify", status_code=204)
async def verify_reset_code(body: VerifyResetCodeRequest, db: AsyncSession = Depends(get_db)):
    # TODO: vérifier le code OTP en cache
    # Pour le dev, tout code est accepté
    return


@auth_router.post("/reset-password", status_code=204)
async def reset_password(body: ResetPasswordWithCodeRequest, db: AsyncSession = Depends(get_db)):
    # TODO: vérifier le code OTP avant de réinitialiser
    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)
    if user:
        await repo.update(user.id, hashed_password=hash_password(body.new_password))


@auth_router.post("/verify-email", status_code=204)
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)
    if user:
        await repo.verify(user.id)


@auth_router.post("/verify-email/resend", status_code=204)
async def resend_verification(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    import random
    otp = str(random.randint(100000, 999999))
    print(f"[DEV] OTP vérification email pour {body.email}: {otp}")
    return


@auth_router.post("/send-verification-code", status_code=204)
async def send_verification_code(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    import random
    otp = str(random.randint(100000, 999999))
    print(f"[DEV] Code vérification pour {body.email}: {otp}")
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
@users_router.put("/me/password", status_code=204)
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


@doctors_router.get("/{doctor_id}/schedule", response_model=WeekScheduleOut)
async def get_doctor_schedule(doctor_id: int, db: AsyncSession = Depends(get_db)):
    repo = DoctorRepository(db)
    doctor = await repo.get_by_id(doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Médecin introuvable")
    sched_repo = ScheduleRepository(db)
    schedules = await sched_repo.get_week_schedule(doctor.id)
    slots = await sched_repo.get_slots(doctor.id)
    return WeekScheduleOut(schedules=schedules, slots=slots)


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
    from ...models.models import FavoriteDoctor
    from sqlalchemy import select
    result = await db.execute(
        select(Doctor)
        .options(selectinload(Doctor.user))
        .join(FavoriteDoctor, FavoriteDoctor.doctor_id == Doctor.id)
        .where(FavoriteDoctor.patient_id == current_user.id)
        .order_by(FavoriteDoctor.created_at.desc())
    )
    doctors = result.scalars().all()
    return [DoctorOut.model_validate(d) for d in doctors]


@favorites_router.post("/{doctor_id}", status_code=201)
async def add_favorite(
    doctor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ...models.models import FavoriteDoctor
    from sqlalchemy import select
    # Vérifier si déjà en favoris
    existing = await db.execute(
        select(FavoriteDoctor).where(
            FavoriteDoctor.patient_id == current_user.id,
            FavoriteDoctor.doctor_id == doctor_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"message": "Déjà en favoris"}
    fav = FavoriteDoctor(patient_id=current_user.id, doctor_id=doctor_id)
    db.add(fav)
    await db.commit()
    return {"message": "Ajouté aux favoris"}


@favorites_router.delete("/{doctor_id}", status_code=204)
async def remove_favorite(
    doctor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ...models.models import FavoriteDoctor
    from sqlalchemy import select, delete
    await db.execute(
        delete(FavoriteDoctor).where(
            FavoriteDoctor.patient_id == current_user.id,
            FavoriteDoctor.doctor_id == doctor_id,
        )
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS  /api/v1/notifications
# ═══════════════════════════════════════════════════════════════════════════════

notifications_router = APIRouter(prefix="/notifications", tags=["Notifications"])
family_router      = APIRouter(prefix="/users", tags=["Family"])
support_router     = APIRouter(prefix="/support", tags=["Support"])


# ═══ NOTIFICATIONS ═══════════════════════════════════════════════════════════

@notifications_router.get("", response_model=NotificationListResponse)
async def get_notifications(
    page: int = Query(1), page_size: int = Query(20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ...models.models import Notification
    from sqlalchemy import select, func
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    total_res = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_res.scalar_one()
    unread_res = await db.execute(
        select(func.count()).where(Notification.user_id == current_user.id,
                                   Notification.is_read == False))
    unread = unread_res.scalar_one()
    stmt = stmt.order_by(Notification.created_at.desc()).offset((page-1)*page_size).limit(page_size)
    result = await db.execute(stmt)
    notifs = result.scalars().all()
    return NotificationListResponse(
        notifications=[NotificationOut.model_validate(n) for n in notifs],
        total=total, unread_count=unread,
    )


@notifications_router.get("/unread/count", response_model=UnreadCountOut)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationRepository(db)
    count = await repo.get_unread_count(current_user.id)
    return UnreadCountOut(count=count)


@notifications_router.put("/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ...models.models import Notification
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == current_user.id)
        .values(is_read=True)
    )
    await db.commit()


@notifications_router.put("/read-all", status_code=204)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ...models.models import Notification
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(Notification).where(Notification.user_id == current_user.id).values(is_read=True)
    )
    await db.commit()


# ═══ FAMILY MEMBERS ══════════════════════════════════════════════════════════

@family_router.get("/me/family-members", response_model=list[FamilyMemberOut])
async def get_family_members(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ...models.models import FamilyMember
    from sqlalchemy import select
    result = await db.execute(
        select(FamilyMember).where(FamilyMember.patient_id == current_user.id)
        .order_by(FamilyMember.created_at.asc())
    )
    return [FamilyMemberOut.model_validate(m) for m in result.scalars().all()]


@family_router.post("/me/family-members", response_model=FamilyMemberOut, status_code=201)
async def add_family_member(
    body: FamilyMemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ...models.models import FamilyMember
    member = FamilyMember(
        patient_id=current_user.id, name=body.name, relation=body.relation,
        date_of_birth=body.date_of_birth, blood_type=body.blood_type,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return FamilyMemberOut.model_validate(member)


@family_router.delete("/me/family-members/{member_id}", status_code=204)
async def delete_family_member(
    member_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ...models.models import FamilyMember
    from sqlalchemy import select
    result = await db.execute(
        select(FamilyMember).where(FamilyMember.id == member_id,
                                    FamilyMember.patient_id == current_user.id)
    )
    member = result.scalar_one_or_none()
    if member:
        await db.delete(member)
        await db.commit()


# ═══ SUPPORT ═════════════════════════════════════════════════════════════════

@support_router.post("/contact", status_code=204)
async def contact_support(body: SupportContactRequest, current_user: User = Depends(get_current_user)):
    print(f"[SUPPORT] De {current_user.email}: {body.subject} — {body.message}")


@support_router.get("/faq")
async def get_faq():
    return {"faqs": [
        {"question": "Comment prendre un rendez-vous ?", "answer": "Recherchez un médecin et sélectionnez un créneau disponible."},
        {"question": "Comment annuler un rendez-vous ?", "answer": "Depuis Mes rendez-vous, ouvrez le détail et cliquez sur Annuler."},
        {"question": "Comment contacter un médecin ?", "answer": "Utilisez la messagerie intégrée depuis le détail de votre RDV."},
        {"question": "Les consultations sont-elles remboursées ?", "answer": "Cela dépend de votre couverture santé. Conservez votre facture."},
    ]}


# ═══ NEARBY DOCTORS ══════════════════════════════════════════════════════════

@doctors_router.get("/nearby", response_model=list[DoctorOut])
async def get_nearby_doctors(
    lat: float = Query(...), lng: float = Query(...),
    radius_km: float = Query(10.0),
    page: int = Query(1), page_size: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    # TODO: ajouter colonnes lat/lng dans Doctor et calculer distance Haversine
    repo = DoctorRepository(db)
    doctors, _ = await repo.search(is_available=True, page=page, page_size=page_size)
    return [DoctorOut.model_validate(d) for d in doctors]
