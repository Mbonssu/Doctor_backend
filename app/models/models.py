from datetime import datetime, timezone
from sqlalchemy import (
    Integer, String, Boolean, Float, DateTime, Text,
    ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.database import Base
import enum


def utcnow():
    return datetime.now(timezone.utc)


# ─── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    patient = "patient"
    doctor  = "doctor"
    admin   = "admin"


class AppointmentStatus(str, enum.Enum):
    pending   = "pending"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"


class AppointmentType(str, enum.Enum):
    consultation  = "consultation"
    follow_up     = "follow_up"
    emergency     = "emergency"
    teleconsult   = "teleconsult"


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id:          Mapped[int]  = mapped_column(Integer, primary_key=True, index=True)
    email:       Mapped[str]  = mapped_column(String(255), unique=True, index=True, nullable=False)
    first_name:  Mapped[str]  = mapped_column(String(100), nullable=False)
    last_name:   Mapped[str]  = mapped_column(String(100), nullable=False)
    phone:       Mapped[str | None] = mapped_column(String(20))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role:        Mapped[str]  = mapped_column(SAEnum(UserRole), default=UserRole.patient, nullable=False)
    is_active:   Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    avatar_url:  Mapped[str | None] = mapped_column(String(500))
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relations
    doctor_profile: Mapped["Doctor | None"] = relationship("Doctor", back_populates="user", uselist=False)
    appointments_as_patient: Mapped[list["Appointment"]] = relationship("Appointment", foreign_keys="Appointment.patient_id", back_populates="patient")
    reviews: Mapped[list["Review"]] = relationship("Review", foreign_keys="Review.patient_id", back_populates="patient")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship("RefreshToken", back_populates="user")


# ─── Doctor profile ───────────────────────────────────────────────────────────

class Doctor(Base):
    __tablename__ = "doctors"

    id:                  Mapped[int]   = mapped_column(Integer, primary_key=True, index=True)
    user_id:             Mapped[int]   = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    specialty:           Mapped[str]   = mapped_column(String(100), nullable=False)
    license_number:      Mapped[str]   = mapped_column(String(50), unique=True, nullable=False)
    years_of_experience: Mapped[int]   = mapped_column(Integer, default=0)
    bio:                 Mapped[str | None] = mapped_column(Text)
    education:           Mapped[str | None] = mapped_column(Text)
    languages:           Mapped[str | None] = mapped_column(String(200))
    hospital_name:       Mapped[str | None] = mapped_column(String(200))
    office_address:      Mapped[str | None] = mapped_column(Text)
    city:                Mapped[str | None] = mapped_column(String(100))
    consultation_fee:    Mapped[float]  = mapped_column(Float, default=0.0)
    is_available:        Mapped[bool]   = mapped_column(Boolean, default=True)
    rating:              Mapped[float]  = mapped_column(Float, default=0.0)
    total_reviews:       Mapped[int]    = mapped_column(Integer, default=0)
    total_patients:      Mapped[int]    = mapped_column(Integer, default=0)
    created_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relations
    user: Mapped["User"] = relationship("User", back_populates="doctor_profile")
    appointments: Mapped[list["Appointment"]] = relationship("Appointment", foreign_keys="Appointment.doctor_id", back_populates="doctor_rel")
    reviews: Mapped[list["Review"]] = relationship("Review", foreign_keys="Review.doctor_id", back_populates="doctor_rel")
    schedules: Mapped[list["DoctorSchedule"]] = relationship("DoctorSchedule", back_populates="doctor")
    time_slots: Mapped[list["DoctorTimeSlot"]] = relationship("DoctorTimeSlot", back_populates="doctor")


# ─── Doctor schedule (configuration semaine) ──────────────────────────────────

class DoctorSchedule(Base):
    __tablename__ = "doctor_schedules"

    id:                   Mapped[int]  = mapped_column(Integer, primary_key=True)
    doctor_id:            Mapped[int]  = mapped_column(ForeignKey("doctors.id"), nullable=False)
    day_of_week:          Mapped[int]  = mapped_column(Integer, nullable=False)  # 0=Lun..6=Dim
    is_working_day:       Mapped[bool] = mapped_column(Boolean, default=True)
    consult_duration_min: Mapped[int]  = mapped_column(Integer, default=30)
    break_duration_min:   Mapped[int]  = mapped_column(Integer, default=10)
    max_patients:         Mapped[int]  = mapped_column(Integer, default=20)
    updated_at:           Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="schedules")


# ─── Doctor time slot (créneau individuel) ────────────────────────────────────

class DoctorTimeSlot(Base):
    __tablename__ = "doctor_time_slots"

    id:         Mapped[int]  = mapped_column(Integer, primary_key=True)
    doctor_id:  Mapped[int]  = mapped_column(ForeignKey("doctors.id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Lun..6=Dim
    time:       Mapped[str]  = mapped_column(String(5), nullable=False)  # "08:30"
    is_active:  Mapped[bool] = mapped_column(Boolean, default=True)

    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="time_slots")


# ─── Appointment ──────────────────────────────────────────────────────────────

class Appointment(Base):
    __tablename__ = "appointments"

    id:                  Mapped[int]      = mapped_column(Integer, primary_key=True, index=True)
    patient_id:          Mapped[int]      = mapped_column(ForeignKey("users.id"), nullable=False)
    doctor_id:           Mapped[int]      = mapped_column(ForeignKey("doctors.id"), nullable=False)
    appointment_date:    Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes:    Mapped[int]      = mapped_column(Integer, default=30)
    appointment_type:    Mapped[str]      = mapped_column(SAEnum(AppointmentType), default=AppointmentType.consultation)
    status:              Mapped[str]      = mapped_column(SAEnum(AppointmentStatus), default=AppointmentStatus.pending)
    consultation_fee:    Mapped[float]    = mapped_column(Float, default=0.0)
    is_paid:             Mapped[bool]     = mapped_column(Boolean, default=False)
    reason:              Mapped[str | None] = mapped_column(Text)
    notes:               Mapped[str | None] = mapped_column(Text)
    payment_method:      Mapped[str | None] = mapped_column(String(50))
    doctor_notes:        Mapped[str | None] = mapped_column(Text)
    cancelled_by:        Mapped[str | None] = mapped_column(String(20))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at:        Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relations
    patient:    Mapped["User"]   = relationship("User", foreign_keys=[patient_id], back_populates="appointments_as_patient")
    doctor_rel: Mapped["Doctor"] = relationship("Doctor", foreign_keys=[doctor_id], back_populates="appointments")


# ─── Review ───────────────────────────────────────────────────────────────────

class Review(Base):
    __tablename__ = "reviews"

    id:         Mapped[int]  = mapped_column(Integer, primary_key=True, index=True)
    doctor_id:  Mapped[int]  = mapped_column(ForeignKey("doctors.id"), nullable=False)
    patient_id: Mapped[int]  = mapped_column(ForeignKey("users.id"), nullable=False)
    rating:     Mapped[int]  = mapped_column(Integer, nullable=False)  # 1-5
    comment:    Mapped[str]  = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    doctor_rel: Mapped["Doctor"] = relationship("Doctor", foreign_keys=[doctor_id], back_populates="reviews")
    patient:    Mapped["User"]   = relationship("User", foreign_keys=[patient_id], back_populates="reviews")


# ─── Refresh token ────────────────────────────────────────────────────────────

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id:         Mapped[int]  = mapped_column(Integer, primary_key=True)
    user_id:    Mapped[int]  = mapped_column(ForeignKey("users.id"), nullable=False)
    token:      Mapped[str]  = mapped_column(String(500), unique=True, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")


# ─── Favorite doctors ─────────────────────────────────────────────────────────

class FavoriteDoctor(Base):
    __tablename__ = "favorite_doctors"

    id:         Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    doctor_id:  Mapped[int] = mapped_column(ForeignKey("doctors.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── Notification ─────────────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id:          Mapped[int]  = mapped_column(Integer, primary_key=True)
    user_id:     Mapped[int]  = mapped_column(ForeignKey("users.id"), nullable=False)
    title:       Mapped[str]  = mapped_column(String(200), nullable=False)
    message:     Mapped[str]  = mapped_column(Text, nullable=False)
    is_read:     Mapped[bool] = mapped_column(Boolean, default=False)
    notif_type:  Mapped[str]  = mapped_column(String(50), default="info")
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── Family member ────────────────────────────────────────────────────────────

class FamilyMember(Base):
    __tablename__ = "family_members"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True)
    patient_id:    Mapped[int]      = mapped_column(ForeignKey("users.id"), nullable=False)
    name:          Mapped[str]      = mapped_column(String(200), nullable=False)
    relation:      Mapped[str]      = mapped_column(String(50), nullable=False)
    date_of_birth: Mapped[str | None] = mapped_column(String(20))
    blood_type:    Mapped[str | None] = mapped_column(String(5))
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
