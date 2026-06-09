from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


# ─── User ─────────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caractères")
        return v


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    role: str = "patient"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caractères")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("patient", "doctor"):
            raise ValueError("Rôle invalide")
        return v


class TokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    """Correspond exactement à AuthResponseModel.fromJson() du Flutter"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str


# ─── Doctor ───────────────────────────────────────────────────────────────────

class DoctorOut(BaseModel):
    id: int
    user_id: int
    specialty: str
    license_number: str
    years_of_experience: int
    bio: Optional[str] = None
    education: Optional[str] = None
    languages: Optional[str] = None
    hospital_name: Optional[str] = None
    office_address: Optional[str] = None
    city: Optional[str] = None
    consultation_fee: float
    is_available: bool
    rating: float
    total_reviews: int
    total_patients: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    user: Optional[UserOut] = None

    model_config = {"from_attributes": True}


class DoctorListResponse(BaseModel):
    doctors: list[DoctorOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class DoctorUpdate(BaseModel):
    specialty: Optional[str] = None
    bio: Optional[str] = None
    education: Optional[str] = None
    languages: Optional[str] = None
    hospital_name: Optional[str] = None
    office_address: Optional[str] = None
    city: Optional[str] = None
    consultation_fee: Optional[float] = None
    is_available: Optional[bool] = None
    years_of_experience: Optional[int] = None


# ─── Schedule ─────────────────────────────────────────────────────────────────

class TimeSlotOut(BaseModel):
    id: int
    doctor_id: int
    day_of_week: int
    time: str
    is_active: bool

    model_config = {"from_attributes": True}


class ScheduleOut(BaseModel):
    id: int
    doctor_id: int
    day_of_week: int
    is_working_day: bool
    consult_duration_min: int
    break_duration_min: int
    max_patients: int

    model_config = {"from_attributes": True}


class ScheduleUpdate(BaseModel):
    day_of_week: int
    is_working_day: bool
    consult_duration_min: int = 30
    break_duration_min: int = 10
    max_patients: int = 20
    slots: list[str] = []  # ["08:00", "08:30", ...]


class WeekScheduleOut(BaseModel):
    schedules: list[ScheduleOut]
    slots: list[TimeSlotOut]


# ─── Appointment ──────────────────────────────────────────────────────────────

class AppointmentOut(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    appointment_date: datetime
    duration_minutes: int
    appointment_type: str
    status: str
    consultation_fee: float
    is_paid: bool
    reason: Optional[str] = None
    notes: Optional[str] = None
    payment_method: Optional[str] = None
    doctor_notes: Optional[str] = None
    cancelled_by: Optional[str] = None
    cancellation_reason: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    doctor: Optional[DoctorOut] = None

    model_config = {"from_attributes": True}


class AppointmentListResponse(BaseModel):
    appointments: list[AppointmentOut]
    total: int
    page: int
    page_size: int


class AppointmentCreate(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_date: datetime
    duration_minutes: int = 30
    appointment_type: str = "consultation"
    reason: Optional[str] = None
    notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    appointment_date: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    appointment_type: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    doctor_notes: Optional[str] = None


class AvailabilityCheckRequest(BaseModel):
    doctor_id: int
    appointment_date: datetime
    duration_minutes: int = 30


class AvailabilityCheckResponse(BaseModel):
    is_available: bool
    message: str


class CancelAppointmentRequest(BaseModel):
    cancellation_reason: str


# ─── Review ───────────────────────────────────────────────────────────────────

class ReviewOut(BaseModel):
    id: int
    doctor_id: int
    patient_id: int
    rating: int
    comment: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    patient: Optional[UserOut] = None

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    reviews: list[ReviewOut]
    total: int
    page: int
    page_size: int
    average_rating: float


class ReviewCreate(BaseModel):
    doctor_id: int
    patient_id: int
    rating: int
    comment: str

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v):
        if not 1 <= v <= 5:
            raise ValueError("La note doit être entre 1 et 5")
        return v


class ReviewUpdate(BaseModel):
    rating: Optional[int] = None
    comment: Optional[str] = None


# ─── Notification ─────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: int
    user_id: int
    title: str
    message: str
    is_read: bool
    notif_type: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UnreadCountOut(BaseModel):
    count: int
